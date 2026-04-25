# Generated migration for PropertyPreference model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('listings', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PropertyPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('preferred_property_types', models.CharField(blank=True, help_text="Comma-separated property types (e.g., 'house,condo')", max_length=255)),
                ('preferred_cities', models.CharField(blank=True, help_text='Comma-separated city names', max_length=500)),
                ('preferred_provinces', models.CharField(blank=True, help_text='Comma-separated province names', max_length=500)),
                ('min_price', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                ('max_price', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True)),
                ('min_bedrooms', models.PositiveIntegerField(blank=True, null=True)),
                ('max_bedrooms', models.PositiveIntegerField(blank=True, null=True)),
                ('min_bathrooms', models.PositiveIntegerField(blank=True, null=True)),
                ('max_bathrooms', models.PositiveIntegerField(blank=True, null=True)),
                ('min_garage', models.PositiveIntegerField(blank=True, null=True)),
                ('min_lot_area', models.DecimalField(blank=True, decimal_places=2, help_text='in sqm', max_digits=10, null=True)),
                ('max_lot_area', models.DecimalField(blank=True, decimal_places=2, help_text='in sqm', max_digits=10, null=True)),
                ('min_floor_area', models.DecimalField(blank=True, decimal_places=2, help_text='in sqm', max_digits=10, null=True)),
                ('max_floor_area', models.DecimalField(blank=True, decimal_places=2, help_text='in sqm', max_digits=10, null=True)),
                ('negotiable_only', models.BooleanField(default=False, help_text='Only show negotiable properties')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('preferred_tags', models.ManyToManyField(blank=True, related_name='preferred_by_users', to='listings.propertytag')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='property_preference', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Property Preference',
                'verbose_name_plural': 'Property Preferences',
            },
        ),
    ]
