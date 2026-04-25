from django import forms
from apps.listings.models import PropertyTag
from .models import PropertyPreference


class PropertyPreferenceForm(forms.ModelForm):
    preferred_tags = forms.ModelMultipleChoiceField(
        queryset=PropertyTag.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Preferred Amenities/Tags"
    )

    class Meta:
        model = PropertyPreference
        fields = [
            'preferred_property_types',
            'preferred_cities',
            'preferred_provinces',
            'min_price',
            'max_price',
            'min_bedrooms',
            'max_bedrooms',
            'min_bathrooms',
            'max_bathrooms',
            'min_garage',
            'min_lot_area',
            'max_lot_area',
            'min_floor_area',
            'max_floor_area',
            'preferred_tags',
            'negotiable_only',
        ]
        widgets = {
            'preferred_property_types': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., house, condo, lot'
            }),
            'preferred_cities': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Tagbilaran, Panglao'
            }),
            'preferred_provinces': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Bohol'
            }),
            'min_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Minimum Price',
                'step': '10000'
            }),
            'max_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Maximum Price',
                'step': '10000'
            }),
            'min_bedrooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Min Bedrooms'
            }),
            'max_bedrooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Max Bedrooms'
            }),
            'min_bathrooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Min Bathrooms'
            }),
            'max_bathrooms': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Max Bathrooms'
            }),
            'min_garage': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Min Garage Spaces'
            }),
            'min_lot_area': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Min Lot Area (sqm)',
                'step': '0.01'
            }),
            'max_lot_area': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Max Lot Area (sqm)',
                'step': '0.01'
            }),
            'min_floor_area': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Min Floor Area (sqm)',
                'step': '0.01'
            }),
            'max_floor_area': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Max Floor Area (sqm)',
                'step': '0.01'
            }),
            'negotiable_only': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
