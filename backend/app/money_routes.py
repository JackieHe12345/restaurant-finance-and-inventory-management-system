"""Preserve monetary JSON number lexemes at the HTTP parsing boundary."""
from decimal import Decimal
import json
from fastapi.routing import APIRoute
from .money import exact_request_numbers

class ExactMoneyRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
            is_json = not content_type or content_type == 'application/json' or content_type.startswith('application/') and content_type.endswith('+json')
            if request.method in {'POST', 'PUT', 'PATCH'} and is_json:
                body = await request.body()
                if body:
                    try:
                        plain = json.loads(body)
                        precise = json.loads(body, parse_float=Decimal)
                        request._json = exact_request_numbers(plain, precise)
                    except (ValueError, TypeError):
                        pass  # Framework supplies its normal invalid-JSON error.
            return await original(request)
        return handler
