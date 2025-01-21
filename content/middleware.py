from django.utils.deprecation import MiddlewareMixin

class AccessControlAllowOriginMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        origin = request.META.get('HTTP_ORIGIN')
        if origin:
            # Dynamically set the allowed origin based on the request's origin
            response["Access-Control-Allow-Origin"] = origin
        else:
            # Fallback if there is no origin in the request (e.g., for non-cross-origin requests)
            response["Access-Control-Allow-Origin"] = "*"
        
        # Add other CORS headers
        response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, PATCH, DELETE"
        response["Access-Control-Allow-Headers"] = "Origin, Content-Type, X-Auth-Token, X-Requested-With, Authorization, x-csrftoken, x-device-id"

        # Handle preflight (OPTIONS) requests
        if request.method == "OPTIONS":
            response.status_code = 200
            response["Content-Length"] = "0"
            return response
        
        return response
