import aiopg
import asyncio
import json
import os
import random
import string
import tornado
import tornado.gen
import tornado.testing
import unittest
import uuid
import nest_asyncio

from tornado.httpclient import AsyncHTTPClient
from tornado.options import define, options

from app import Application


def random_vin():
    """
    Generates a test vin
    """
    chars = string.ascii_uppercase + \
            string.ascii_lowercase + \
            string.digits
    return ''.join(random.choice(chars) for _ in range(17))


class TestBase(tornado.testing.AsyncHTTPTestCase):

    def setUp(self):
        super().setUp()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.reset())

    def tearDown(self):
        super().tearDown()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.app.close_db())

    async def reset(self):
        async with self.get_db() as pool:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute('DELETE FROM vehicles')
                conn.close()

    def get_db(self):
        '''
        Instantiate the database.
        '''
        #               - PORT=3000
        #               - IN_DOCKER=true
        #               - DB_HOST=db
        #               - DB_PORT=5432
        #               - DB_PASS=docker
        #               - DB_USER=postgres
        #               - DB_DATABASE=vinli_interview

        return aiopg.create_pool(
            host=options.db_host,
            port=options.db_port,
            user=options.db_user,
            password=options.db_password,
            dbname=options.db_database)

    def get_app(self):
        self.app = Application()
        return self.app


class TestPing(TestBase):
    def test_get_route(self):
        response = self.fetch(self.get_url('/ping'))
        self.assertEqual(200, response.code)
        self.assertEqual(b'{"ping": "pong"}', response.body)


class VehicleCreate(TestBase):
    """
    Tests on the POST /api/v1/vehicles routes
    """

    def test_vin_should_be_correct_length(self):
        """
        Ensure a VIN has a length of 17 characters
        """
        payload = {
            "vehicle": {
                "vin": random_vin()[0:10],
                "make": "Ford",
                "model": "Focus",
                "year": 2010
            }
        }

        response = self.fetch(
            self.get_url('/api/v1/vehicles'),
            method='POST',
            body=json.dumps(payload),
            headers={'content-type': 'application/json'}
        )

        self.assertEqual(response.code, 400)

    def test_unique_vin(self):
        """
        Ensure a VIN can only be written to the database once.
        """
        payload = {
            "vehicle": {
                "vin": random_vin(),
                "make": "Ford",
                "model": "Focus",
                "year": 2010
            }
        }

        response = self.fetch(
            self.get_url('/api/v1/vehicles'),
            method='POST',
            body=json.dumps(payload),
            headers={'content-type': 'application/json'}
        )

        self.assertEqual(response.code, 201)

        response = self.fetch(
            self.get_url('/api/v1/vehicles'),
            method='POST',
            body=json.dumps(payload),
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 400)

    def test_create_vehicle(self):
        """
        Ensure a vehicle is properly created
        """
        payload = {
            "vehicle": {
                "vin": random_vin(),
                "make": "Ford",
                "model": "Focus",
                "year": 2010
            }
        }

        response = self.fetch(
            self.get_url('/api/v1/vehicles'),
            method='POST',
            body=json.dumps(payload),
            headers={'content-type': 'application/json'}
        )

        self.assertEqual(response.code, 201)

        vehicle = json.loads(response.body.decode()).get('vehicle', None)
        self.assertIsNot(vehicle, None)

        self.assertEqual(vehicle.get('vin'), payload['vehicle']['vin'])
        self.assertEqual(vehicle.get('make'), 'Ford')
        self.assertEqual(vehicle.get('model'), 'Focus')
        self.assertEqual(vehicle.get('year'), 2010)
        self.assertNotEqual(vehicle.get('id'), "")
        self.assertNotIn('notes', vehicle.keys())


class VehiclesList(TestBase):
    """
    Tests on the GET /api/v1/vehicles route
    """

    async def create_vehicles(self):
        vehicles = [
            (random_vin(), 'Tesla', 'Model S', 2018, '',),
            (random_vin(), 'Ford', 'Escort', 1996, '',)
        ]

        qry = '''
            INSERT INTO vehicles (vin, make, model, year, notes)
            VALUES (%s, %s, %s, %s, %s)'''

        async with self.get_db() as pool:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    for i in vehicles:
                        await cur.execute(qry, i)
                conn.close()

    def test_get_vehicles_list(self):
        """
        Ensure a list of vehicles can properly be retrieved
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.create_vehicles())

        response = self.fetch(
            self.get_url('/api/v1/vehicles'),
            headers={'content-type': 'application/json'}
        )

        self.assertEqual(response.code, 200)

        vehicles = json.loads(response.body.decode()).get('vehicles', None)
        self.assertEqual(len(vehicles), 2)

    def test_accept_vin_query_param_to_filter(self):
        """
        Ensure it accepts a query param to filter by exact VIN
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.create_vehicles())
        response = self.fetch(
            self.get_url('/api/v1/vehicles?vin=esl'),
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 200)
        vehicles = json.loads(response.body.decode()).get('vehicles', None)
        self.assertEqual(len(vehicles), 0)

    def test_accept_make_query_param_to_filter(self):
        """
        Ensure it accepts a query param to filter by Make
        with partial match
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.create_vehicles())
        response = self.fetch(
            self.get_url('/api/v1/vehicles?make=esl'),
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 200)
        vehicles = json.loads(response.body.decode()).get('vehicles', None)
        self.assertEqual(len(vehicles), 1)


class VehiclesDetail(TestBase):
    """
    Tests on the GET /api/v1/vehicles/{vehicleId} route
    """
    async def create_vehicle(self):
        vehicle = (random_vin(), 'Tesla', 'Model S', 2018, '',)

        qry = 'INSERT INTO vehicles (vin, make, model, year, notes) VALUES (%s, %s, %s, %s, %s)'

        async with self.get_db() as pool:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(qry, vehicle)
                    await cur.execute('SELECT * from vehicles')
                    added = await cur.fetchall()
                    self.vehicle_id = added[0][0]
                conn.close()

    def test_get_vehicle_detail(self):
        """
        Ensure that it can retrieve a vehicle that exists
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.create_vehicle())
        vehicle_id = str(self.vehicle_id)
        response = self.fetch(
            self.get_url(f'/api/v1/vehicles/{vehicle_id}'),
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 200)
        resp = json.loads(response.body.decode())
        self.assertIsNotNone(resp)

    def test_vehicle_non_existence(self):
        """
        Ensure that it returns an appropriate error if the vehicle
        does not exist
        """
        # invalid uuid should raise 400
        response = self.fetch(
            self.get_url(f'/api/v1/vehicles/some-bad-uuid'),
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 400)

        # 404 should be raised for non-existing uuid
        u = str(uuid.uuid4())
        response = self.fetch(
            self.get_url(f'/api/v1/vehicles/{u}'),
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 404)


class VehiclesDelete(TestBase):
    """
    Tests on the DELETE /api/v1/vehicles/{vehicleId} route
    """
    async def create_vehicle(self):
        vehicle = (random_vin(), 'Tesla', 'Model S', 2018, '',)

        qry = 'INSERT INTO vehicles (vin, make, model, year, notes) VALUES (%s, %s, %s, %s, %s)'

        async with self.get_db() as pool:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(qry, vehicle)
                    await cur.execute('SELECT * from vehicles')
                    added = await cur.fetchall()
                    self.vehicle_id = added[0][0]
                conn.close()

    def test_delete_vehicle(self):
        """
        Ensure that it can delete a vehicle that exists
        """
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.create_vehicle())
        vehicle_id = str(self.vehicle_id)
        response = self.fetch(
            self.get_url(f'/api/v1/vehicles/{vehicle_id}'),
            method='DELETE',
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 200)
        resp = json.loads(response.body.decode())
        self.assertIsNotNone(resp)

    def test_delete_vehicle_non_existing(self):
        """
        Ensure that it displays an appropriate error if a vehicle
        does not exist.
        """
        response = self.fetch(
            self.get_url(f'/api/v1/vehicles/some-bad-uuid'),
            method='DELETE',
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 400)

        # 404 should be raised for non-existing uuid
        u = str(uuid.uuid4())
        response = self.fetch(
            self.get_url(f'/api/v1/vehicles/{u}'),
            method='DELETE',
            headers={'content-type': 'application/json'}
        )
        self.assertEqual(response.code, 404)


if __name__ == '__main__':
    nest_asyncio.apply()
    unittest.main()
