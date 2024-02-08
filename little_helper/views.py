from django.shortcuts import render
from django.http import HttpResponse

def index(request):
    with open('index.html', 'r') as file:
        html_content = file.read()
    return HttpResponse(html_content)