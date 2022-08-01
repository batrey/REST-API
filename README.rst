==============================
==============================

This is a partially implemented REST API that resembles services built.

Python 3.6 with the "new" asynchronous features of Python, and
utilizes the `Tornado <http://tornadoweb.org>`_.

---------------
Getting Started
---------------


With Python Docker
^^^^^^^^^^^^^^^^^^

::

    $ docker-compose up -d db
    $ docker-compose up app

The application will now be running on ``http://localhost:3000``.  eg::


    ➜  ~ curl localhost:3000/ping
    {
        "ping": "pong"
    }

To run tests, execute::

    $ docker-compose run app coverage run tests.py
    $ docker-compose run app python tests.py
    # to see the code coverage with missing lines
    $ docker-compose run app coverage report -m
    

----------
Objectives
----------

- Get all implemented tests to pass
- Implement stubbed out tests
- Write new tests to reach 100% code coverage

----------
Guidelines
----------

