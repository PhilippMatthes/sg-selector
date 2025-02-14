import json

from composer.models import Route
from django.conf import settings
from django.contrib.gis.geos import LineString, Point
from django.contrib.gis.measure import D
from django.core.management.base import BaseCommand
from routing.models import LSA
from tqdm import tqdm


class Command(BaseCommand):
    help = """
        Loads the example data into the database.

        The example data should have the format:
        [
            {
                "route": [
                    {
                        "lon": float,
                        "lat": float,
                        "alt": float
                    }, ...
                ]
            }, ...
        ]
    """

    def add_arguments(self, parser):
        # Add an argument to the parser that
        # specifies the path to the file to load
        parser.add_argument('path', type=str)

        # Add flag which forces the command
        # to append the routes to the database
        parser.add_argument('--append', action='store_true')

    def handle(self, *args, **options):
        # Check if the path argument is valid
        if not options["path"]:
            raise Exception("Please specify a path to the file to load.")

        # Load the file
        with open(options["path"]) as f:
            data = json.load(f)

        # If there is only one route in the data, we need to wrap it in a list
        if isinstance(data, dict):
            data = [data]

        if not LSA.objects.exists():
            raise Exception("LSAs need to be loaded first!")

        routes_exist = Route.objects.exists()
        if not routes_exist or options["append"]:
            if options["append"] and routes_exist:
                print("CAUTION: Appending to existing routes!")
                print("Do not create route bindings for the routes you are appending!")

            base_id = 0 if not routes_exist else Route.objects.order_by("-id").first().id + 1

            routes = []
            for route_id, route_json in tqdm(enumerate(data), desc="Loading example routes"):
                route = self.load_route(base_id + route_id, route_json)
                routes.append(route)

            # Check which routes are too far away from any LSA
            routes_to_remove = set()
            for route in tqdm(routes, desc="Checking routes"):
                lsa_in_proximity = LSA.objects \
                    .filter(geometry__dwithin=(route.geometry, D(m=settings.SEARCH_RADIUS_M))) \
                    .exists()
                if not lsa_in_proximity:
                    routes_to_remove.add(route.id)
            print(f"{len(routes_to_remove)} routes will not be included due to no LSA in proximity.")

            Route.objects.bulk_create([route for route in routes if route.id not in routes_to_remove])

        print(f"{Route.objects.count()} example routes in database.")


    def load_route(self, route_id, route_json):
        """
        Load the given route into the database.
        """

        points = []
        for coordinate_dict in route_json["route"]:
            point = Point(coordinate_dict["lon"], coordinate_dict["lat"], srid=settings.LONLAT)
            points.append(point)
        linestring = LineString(points, srid=settings.LONLAT)

        return Route(id=route_id, geometry=linestring)
