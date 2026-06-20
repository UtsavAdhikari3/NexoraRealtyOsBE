from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Property,PropertyMedia
from .serializers import PropertySerializer, PropertyMediaSerializer
from django.shortcuts import get_object_or_404



class PropertyListCreateView(
    generics.ListCreateAPIView
):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Property.objects.filter(
            agency=self.request.user.agency
        )

    def perform_create(self, serializer):
        serializer.save(
            agency=self.request.user.agency
        )


class PropertyDetailView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Property.objects.filter(
            agency=self.request.user.agency
        )
    
class PropertyMediaListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyMediaSerializer
    permission_classes = [IsAuthenticated]

    def get_property(self):
        return get_object_or_404(
            Property,
            id=self.kwargs["property_id"],
            agency=self.request.user.agency
        )

    def get_queryset(self):
        property_obj = self.get_property()

        return PropertyMedia.objects.filter(
            agency=self.request.user.agency,
            property=property_obj
        ).order_by("sort_order", "-created_at")

    def perform_create(self, serializer):
        property_obj = self.get_property()

        serializer.save(
            agency=self.request.user.agency,
            property=property_obj
        )


class PropertyMediaDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyMediaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PropertyMedia.objects.filter(
            agency=self.request.user.agency
        )