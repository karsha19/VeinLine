from rest_framework import generics, permissions
from rest_framework.response import Response

from .serializers import RegisterSerializer, UserMeSerializer


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer


class MeView(generics.RetrieveAPIView):
    serializer_class = UserMeSerializer

    def get(self, request, *args, **kwargs):
        return Response(UserMeSerializer(request.user).data)

from django.shortcuts import render

# Create your views here.
