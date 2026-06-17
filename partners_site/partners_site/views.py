from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def exam_landing_view(request: HttpRequest) -> HttpResponse:
    """Render the standalone exam landing page.

    Args:
        request: Incoming HTTP request.

    Returns:
        Rendered landing page response.
    """
    return render(request, "landing/exam.html")
