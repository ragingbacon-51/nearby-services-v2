from django.db import migrations


def create_categories(apps, schema_editor):
    category = apps.get_model("marketplace", "Category")
    for name in (
        "Tuition", "Plumbing", "Electrical", "Babysitting", "Laundry & Dry Cleaning",
        "Salons & Beauty", "Auto Repair & Mechanics", "Electronics & Phone Repair",
    ):
        category.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0001_initial")]
    operations = [migrations.RunPython(create_categories, migrations.RunPython.noop)]
