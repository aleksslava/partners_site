from pathlib import Path

from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
BASE_DIR = Path(__file__).resolve().parent.parent

# Create your views here.

def catalog(request):
    return render(request, 'shop/index.html')
    # return render(request, f'{BASE_DIR}/templates/base.html')
