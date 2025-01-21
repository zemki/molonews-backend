import datetime
from django.http import HttpResponse
import requests
from rest_framework.views import APIView
from rest_framework.response import Response

class RedirectView(APIView):
    def get(self, request, *args, **kwargs):
        tracking_params = request.query_params

        # create a log file in the root dir with the tracking_params 
        with open('logs/log-qr.html', 'a') as f:
            # get the first key out of the tracking_params
            key = list(tracking_params.keys())[0]
            # create a log string containing the tracking_params and the user agent and the datetime
            logstring =  str(datetime.datetime.now()) + ";" + str(key) + ";" + request.META['HTTP_USER_AGENT'] + "</br>"
            # add a new line character to the logstring
            logstring += "\n"
            # write the log string to the log file
            f.write(str(logstring))
            # close the file
            f.close()
            
        # if tracking_params contain t-shirt then goto this page
        #if 't-shirt' in tracking_params:
        #    redirect_url = redirect_to_website(tracking_params)
        #else:
        #    redirect_url = "https://molo.news/"

        # iOS Store Link:
        redirect_url_ios = "https://apps.apple.com/de/app/molo-news/id1486601544"
        # Android Store Link:
        redirect_url_android = "https://play.google.com/store/apps/details?id=news.molo.android&pli=1"

        # if the user agent contains iPhone or iPad then redirect to the iOS Store Link
        if 'iPhone' in request.META['HTTP_USER_AGENT'] or 'iPad' in request.META['HTTP_USER_AGENT']:
            redirect_url = redirect_url_ios
        # if the user agent contains Android then redirect to the Android Store Link
        elif 'Android' in request.META['HTTP_USER_AGENT']:
            redirect_url = redirect_url_android
        # if the user agent contains Linux then redirect to the molo.news page
        else:
            redirect_url = "https://molo.news/"
        
        html = """
                <html>
                <head>
                    <meta http-equiv="refresh" content="0; url=""" + redirect_url + """">
                </head>
                <body>
                <a href='""" + redirect_url + """'>klicke hier um auf die molo.news Seite zu gelangen.</a>
                
                <script>
                    window.location.href = '""" + redirect_url + """';
                </script>
                </body>
                </html>
             """
        
        
    
        
        if redirect_url:
            return HttpResponse(html)
        else:
            return Response("Error occurred", status=500)

def redirect_to_website(tracking_params):

    url = "https://molo.news"
    
    # Send a GET request to the redirect URL
    response = requests.get(url)

    # Check if the request was successful (status code 200)
    if response.status_code == 200:
        # Redirect the user to the website
        return response.url
    else:
        # Handle the error
        return None