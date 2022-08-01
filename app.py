#!/usr/bin/env python3
import aiopg
import json
import os
import uuid
import psycopg2
import asyncio
import tornado.locks
import tornado.web
from tornado.gen import coroutine
import nest_asyncio

from tornado.options import define, options

define("port", default=3000, help="run on the given port", type=int)
define("db_host", 
        default=os.getenv('DB_HOST', default='localhost'), 
        help="database host")

define("db_port", 
        default=os.getenv('DB_PORT', default='5432'), 
        help="database port")

define("db_database", 
        default=os.getenv('DB_DATABASE', default='vinli_interview'), help="database name")

define("db_user", default=os.getenv('DB_USER', 'postgres'), 
        help="database user")
define("db_password", default=os.getenv('DB_PASS', 'docker'), 
        help="database password")


class NoResultError(Exception):
    pass

class Application(tornado.web.Application):
    def __init__(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.get_db())
        handlers = [
            (r'/ping', PingHandler),
            (r'/api/v1/vehicles', VehiclesHandler),
            (r'^/api/v1/vehicles/(.*)$', VehicleDetailHandler),
        ]

        settings = dict(
            debug=False,
        )

        super(Application, self).__init__(handlers, **settings)

    async def get_db(self):
        self.db = await aiopg.create_pool(
            host=options.db_host,
            port=options.db_port,
            user=options.db_user,
            password=options.db_password,
            dbname=options.db_database)

    async def close_db(self):
        async with self.db as pool:
            pool.close()


class BaseHandler(tornado.web.RequestHandler):
    """
    Base handlers that houses some helper methods
    """
    @property
    def json(self):
        if getattr(self, '_json', None) is None:
            self._json = json.loads(self.request.body)
        return self._json

    async def get_json_argument(self, item, deft=None):
        """
        Retrieves an item from request JSON body with an optional
        default value.
        """
        return self.json.get(item, deft)

    def row_to_obj(self, row, cur):
        """
        Convert a SQL row to an object supporting dict and attribute access
        """
        obj = tornado.util.ObjectDict()
        for val, desc in zip(row, cur.description):
            obj[desc.name] = val
        return obj

    async def execute(self, stmt, *args):
        """
        Execute a SQL statement.
        Must be called with ``await self.execute(...)``
        """
        async with self.application.db.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(stmt, args)

    async def delete_query(self, stmt, *args):
        async with self.application.db.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(stmt, args)
                return cur.rowcount

    async def query(self, stmt, *args):
        """
        Query for a list of results.
        Typical usage::
            results = await self.query(...)
        Or::
            for row in await self.query(...)
        """

        async with self.application.db.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(stmt, args)
                return [self.row_to_obj(row, cur)
                        for row in await cur.fetchall()]

    async def queryone(self, stmt, *args):
        """
        Query for exactly one result.
        Raises NoResultError if there are no results, or ValueError if
        there are more than one.
        """
        results = await self.query(stmt, *args)
        if len(results) == 0:
            raise NoResultError()
        elif len(results) > 1:
            raise ValueError("Expected 1 result, got %d" % len(results))
        return results[0]


class PingHandler(tornado.web.RequestHandler):
    """
    Handler to serve /ping route
    """
    async def get(self):
        self.write({'ping': 'pong'})


class VehicleDetailHandler(BaseHandler):
    """
    Handles routes on ``/api/v1/vehicles/{vehicleId}``
    """
    async def get(self, vehicle_id=None):
        """
        Retrieve a single vehicle
        """
        # check if vehicle_id is a valid uuid
        if not is_valid_uuid(vehicle_id):
            self.set_status(400)
            self.write({'message': 'vehicle id is not a valid uuid'})
            return

        try:
            vehicle = await self.queryone('SELECT * from vehicles where id=%s', vehicle_id)
        except NoResultError:
            self.set_status(404)
            self.write({'message': 'vehicle not found'})
            return
        self.write({**vehicle, 'id': str(vehicle['id']), 'created_at': str(vehicle['created_at']), 'updated_at': str(vehicle['updated_at'])})

    async def delete(self, vehicle_id=None):
        """
        Delete a single vehicle.
        """
        if not is_valid_uuid(vehicle_id):
            self.set_status(400)
            self.write({'message': 'vehicle id is not a valid uuid'})
            return

        resp = await self.delete_query('DELETE from vehicles where id=%s', vehicle_id)
        if resp == 0:
            self.set_status(404)
            self.write({'message': 'vehicle not found'})
            return
        self.write({'message': 'vehicle deleted'})


class VehiclesHandler(BaseHandler):
    """
    Handles routes on ``/api/v1/vehicles``
    """

    async def get(self):
        """
        Retrieve a list of vehicles
        """
        vin = self.get_query_argument('vin', None)
        make = self.get_query_argument('make', None)
        if vin is not None:
            resp = await self.query('SELECT * from vehicles where vin=%s', vin)
        elif make is not None:
            resp = await self.query('SELECT * from vehicles where make like %s', f'%{make}%')
        else:
            resp = await self.query('SELECT * from vehicles')
        vehicles = [{**x,
                     'id': str(x['id']),
                     'created_at': str(x['created_at']),
                     'updated_at': str(x['updated_at']),
                     } for x in list(resp)]
        self.write({'vehicles': vehicles})

    async def post(self):
        """
        Create a new vehicle
        """
        vehicle = {
            'vin': None,
            'notes': 'super secret field no one should see',
            'year': None,
            'make': None,
            'model': None,
        }

        req = await self.get_json_argument('vehicle')

        # need to check vin has length of 17
        if len(req['vin']) != 17:
            self.set_status(400)
            self.write({'message': 'incorrect vin length'})
            return

        vehicle.update(req)
        # need to check for duplicate vehicles via vin
        resp = await self.query('SELECT * from vehicles where vin=%s', req['vin'])
        if len(resp) != 0:
            self.clear()
            self.set_status(400)
            self.write({'message': 'duplicate vin'})
            return

        if vehicle["year"] is not None and vehicle["year"] > 1994:
            vehicle["notes"] = "too old for OBD II"

        resp = await self.query(
            'INSERT INTO vehicles (vin, make, model, year, notes) '
            'VALUES (%s, %s, %s, %s, %s) '
            'RETURNING id, created_at, updated_at',
            vehicle['vin'], vehicle['make'], vehicle['model'],
            vehicle['year'], vehicle['notes']
        )

        if len(resp) == 1:
            vehicle.update({
                'id': str(resp[0]['id']),
                'created_at': str(resp[0]['created_at']),
                'updated_at': str(resp[0]['updated_at']),
            })
            vehicle.pop('notes')

            self.set_status(201)
            self.write({'vehicle': vehicle})
            return


async def main():
    tornado.options.parse_command_line()
    app = Application()
    app.listen(options.port)

    shutdown_event = tornado.locks.Event()
    await shutdown_event.wait()

def is_valid_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

if __name__ == '__main__':
    nest_asyncio.apply()
    tornado.ioloop.IOLoop.current().run_sync(main)
