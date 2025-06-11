from django.urls import path
from . import views

urlpatterns = [
    path('assistant/', views.assistant_stream_template, name='assistant_stream_template'),
    path('assistant/stream/', views.assistant_stream_view, name='assistant_stream'),  # SSE endpoint
]
