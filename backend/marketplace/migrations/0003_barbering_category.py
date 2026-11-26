from django.db import migrations


def create_category(apps, schema_editor):
    category = apps.get_model("marketplace", "Category")
    category.objects.get_or_create(name="Barbering & Shaving")


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0002_initial_categories")]
    operations = [migrations.RunPython(create_category, migrations.RunPython.noop)]
