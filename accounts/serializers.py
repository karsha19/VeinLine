from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Profile, UserRole
from donations.models import DonorDetails

User = get_user_model()


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["role", "phone_e164", "city", "area"]


class UserMeSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "profile"]


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=UserRole.choices)

    # Profile
    phone_e164 = serializers.CharField(required=False, allow_blank=True, max_length=20)
    city = serializers.CharField(required=False, allow_blank=True, max_length=64)
    area = serializers.CharField(required=False, allow_blank=True, max_length=64)

    # Donor details
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=120)
    age = serializers.IntegerField(required=False, min_value=18, max_value=80)
    blood_group = serializers.CharField(required=False, allow_blank=True, max_length=3)

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def validate(self, attrs):
        role = attrs.get("role")
        if role == UserRole.DONOR:
            for f in ["full_name", "age", "blood_group", "city"]:
                if not attrs.get(f):
                    raise serializers.ValidationError({f: "Required for donor registration."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role")

        phone_e164 = validated_data.pop("phone_e164", "")
        city = validated_data.pop("city", "")
        area = validated_data.pop("area", "")

        full_name = validated_data.pop("full_name", "")
        age = validated_data.pop("age", None)
        blood_group = validated_data.pop("blood_group", "")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=password,
        )
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        user.save()
        user.profile.role = role
        user.profile.phone_e164 = phone_e164
        user.profile.city = city
        user.profile.area = area
        user.profile.save()

        if role == UserRole.DONOR:
            DonorDetails.objects.update_or_create(
                user=user,
                defaults={
                    "full_name": full_name,
                    "age": age,
                    "blood_group": blood_group,
                    "city": city,
                    "area": area,
                },
            )

        return user


