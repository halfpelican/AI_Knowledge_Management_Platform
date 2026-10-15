"""Content negotiation for the one route that does not answer in JSON.

``IgnoreClientContentNegotiation`` is DRF's documented example of custom content negotiation
(api-guide/content-negotiation, "Example"), used by FR-15's download alone (D-75).
"""

from rest_framework.negotiation import BaseContentNegotiation


class IgnoreClientContentNegotiation(BaseContentNegotiation):
    """Select the view's first parser and renderer whatever the request's ``Accept`` says.

    **Why the download needs it.** DRF negotiates in ``APIView.initial()``, before
    authentication and before the view method runs, and this project's only renderer is
    ``JSONRenderer``. A client asking for the file it is downloading, ``Accept:
    application/pdf``, matches no renderer, so DRF answered 406 without ever reaching the
    view, even though the view answers with a ``FileResponse`` that no renderer touches. A
    browser following the link sends its navigation header, which ends in ``*/*`` and so was
    never refused; a download manager or a script that names the type was.

    **What it does not change.** The route's errors (401, 404) are still rendered by
    ``JSONRenderer``, as every other error in the API is, and every other route still
    negotiates normally: ``test_there_is_no_browsable_api`` still holds.
    """

    def select_parser(self, request, parsers):
        return parsers[0]

    def select_renderer(self, request, renderers, format_suffix=None):
        return (renderers[0], renderers[0].media_type)
