"""Serializers for the API contract (docs/api-contract.md).

``UserSerializer`` is the one user object every endpoint returns. It never carries
``password_hash``, ``failed_attempts`` or ``locked_until``; a test asserts the exact
key set so a field cannot leak in later.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Role
from apps.core.constants import ROLE_NAMES
from apps.core.models import NAME_MAX_LENGTH
from apps.documents.models import Document

User = get_user_model()

USER_FIELDS = ("id", "name", "email", "role", "created_at")


class UserSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role.role_name", read_only=True)

    class Meta:
        model = User
        fields = USER_FIELDS
        read_only_fields = USER_FIELDS


# --- FR-01, FR-02 -------------------------------------------------------------------


class RegisterSerializer(serializers.Serializer):
    """FR-01 request body. The role is never accepted from the client: registration
    always creates an Employee (docs/schema-v1.md Users.role_id)."""

    name = serializers.CharField(max_length=NAME_MAX_LENGTH)
    # Bounded by the column itself, so the two cannot drift. Without the bound an
    # over-long address passes validation and the INSERT raises DataError, which is
    # a sibling of IntegrityError rather than a subclass, so the 409 handler below
    # does not catch it and an anonymous caller gets a 500 instead of the 400 the
    # contract names.
    email = serializers.EmailField(max_length=User._meta.get_field("email").max_length)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        return value.lower()  # D-02: the address is unique case-insensitively

    def validate(self, attrs):
        # AUTH_PASSWORD_VALIDATORS run against the would-be user so the similarity
        # validator can compare the password with the name and the address.
        candidate = User(name=attrs["name"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages})
        return attrs


class LoginSerializer(serializers.Serializer):
    """FR-02 request body. FR-02 Server-End, Validation rules: "required field check
    on both inputs. Email format checked before database lookup" — and the UC-02
    pseudocode is explicit that a malformed address is 400 ("IF NOT
    isValidEmailFormat(submittedEmail) THEN RETURN response(400, ...)"), before the
    account is read. A 400 on malformed syntax discloses nothing, because it is
    returned whether or not the address is registered; the generic 401 is kept for a
    well-formed address that is unknown and for a wrong password, which is where the
    enumeration protection actually lives (D-02). Bounded by the column length, as
    the registration serializer is, so the two agree."""

    email = serializers.EmailField(max_length=User._meta.get_field("email").max_length)
    password = serializers.CharField(trim_whitespace=False)

    def validate_email(self, value):
        return value.strip().lower()  # D-02


# --- FR-05 ----------------------------------------------------------------------------


class RoleSerializer(serializers.ModelSerializer):
    """``GET /api/roles`` item: the role, its permission codes (D-14) and the
    ``role_id`` FR-05's request body carries, which the client reads from here."""

    role_id = serializers.UUIDField(source="id", read_only=True)
    name = serializers.CharField(source="role_name", read_only=True)
    permissions = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="permission_name"
    )

    class Meta:
        model = Role
        fields = ("role_id", "name", "description", "permissions")
        read_only_fields = fields


class RoleChangeSerializer(serializers.Serializer):
    """``PATCH /api/users/{id}/role`` body. FR-05 Server-End: "Receives { user_id,
    new_role_id } from an authenticated Admin session only", and "new_role_id must
    exist in Roles table". The user id is the one in the path, which carries the same
    information. A missing or non-UUID ``role_id`` is a malformed body and is 400
    here; a well-formed id that names no row is 404, which the view decides, because
    "404 Not Found if user/role doesn't exist" is FR-05's own response for it."""

    role_id = serializers.UUIDField()


# --- FR-08 document upload ------------------------------------------------------------


class DocumentSerializer(serializers.ModelSerializer):
    """The document object every FR-08 and FR-15 endpoint returns.

    ``doc_id`` rather than ``id``, matching the proposal's Documents table and the
    ``201 Created with the document ID`` FR-08 promises. ``file_path`` is never
    exposed: it is a path inside MEDIA_ROOT and the client has no use for it, while
    publishing it invites a caller to construct one. ``content_hash`` is likewise
    internal — it exists to answer 409, and echoing it would let a caller probe
    whether a document they cannot see has already been uploaded.
    """

    doc_id = serializers.UUIDField(source="id", read_only=True)
    uploaded_by = serializers.CharField(source="uploaded_by.email", read_only=True)

    class Meta:
        model = Document
        fields = ("doc_id", "title", "file_type", "status", "uploaded_at", "department",
                  "visible_to_roles", "file_size_bytes", "uploaded_by")
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    """FR-08 request body, sent as ``multipart/form-data``.

    Field shapes only. The *order* of the rejections is the view's, because the
    proposal's section 7.2 ``validateUpload()`` fixes it — contribute permission,
    then signature, then size, then title, then duplicate — and a serializer would
    report them all at once in whichever order its fields happen to sit.
    """

    file = serializers.FileField()
    title = serializers.CharField(max_length=NAME_MAX_LENGTH, allow_blank=False,
                                  trim_whitespace=True)
    department = serializers.CharField(max_length=NAME_MAX_LENGTH, required=False,
                                       allow_blank=True, default="")
    # docs/decisions.md D-29. Omitted means both roles: a document nobody thought
    # about is visible to everybody, so an omitted field can never accidentally hide
    # content. Present but empty is 400 (``allow_empty=False``) — "visible to
    # nobody" is not something anyone means to ask for, and FR-11 would filter such a
    # document out of every search in silence. A name outside ROLE_NAMES is 400.
    visible_to_roles = serializers.ListField(
        child=serializers.ChoiceField(choices=ROLE_NAMES),
        required=False,
        allow_empty=False,
    )

    def validate_visible_to_roles(self, value):
        # Stored in ROLE_NAMES order and deduplicated, so two requests naming the
        # same roles differently produce the same row and the FR-11 predicate has
        # one shape to match.
        return [name for name in ROLE_NAMES if name in set(value)]
