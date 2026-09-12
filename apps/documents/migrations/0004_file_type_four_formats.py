# docs/decisions.md D-15: exactly four upload formats. Legacy DOC and XLS need an
# external binary to extract and would always be answered 415, so they are dropped
# from ACCEPTED_FORMATS and from the Document.file_type vocabulary.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0003_tags'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='file_type',
            field=models.CharField(choices=[('docx', 'docx'), ('pdf', 'pdf'), ('txt', 'txt'), ('xlsx', 'xlsx')], max_length=32),
        ),
    ]
