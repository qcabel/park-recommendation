#!/usr/bin/env python

from argparse import ArgumentParser
from collections import deque, namedtuple
from dataclasses import dataclass, replace
import json
import sqlite3
import asyncio

import popular_times

from datetime import datetime
from tornado import gen
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.ioloop import IOLoop, PeriodicCallback
import tornado.queues
import sanic
import prometheus_client
import tqdm

# TODO:

# 1. prometheus_client for metrics
# 2. an event loop to trigger scrapes based on fixed interval
# 3. an HTTP server so that we can see the stats (and provide an interface into the underlying DB, perhaps)


@dataclass
class Task:
    id: str
    name: str
    address: str
    batch_id: int = 0


class DatabaseConnectionProvider:
    @property
    def get_connection(self) -> sqlite3.Connection:
        """
        Get the current DB connection.
        :return:
        """
        raise NotImplementedError()


class StaticDatabaseConnectionProvider(DatabaseConnectionProvider):
    def __init__(self, conn):
        self.conn = conn

    @property
    def get_connection(self):
        return self.conn


class Metrics:
    def __init__(self):
        self.counter = prometheus_client.Counter(
            "popular_times_scrape_count",
            "The counter to keep track how many times we've queried Google for popular times",
            ('has_current_popularity', 'status')
        )

    def observe(self, result: popular_times.PopularTimes):
        pass


class PopularTimesClient:
    def __init__(self):
        self._client = AsyncHTTPClient()

    async def get_popular_times_by_name_addr(self, name, address):
        search_url = popular_times.build_populartimes_url(name, address)
        resp = await self._client.fetch(
           HTTPRequest(search_url, headers=popular_times.USER_AGENT, validate_cert=False)
        )
        resp_str = resp.body.decode('utf-8')

        return popular_times.parse_populartimes(resp_str, address)


class PopularTimesScraper:
    def __init__(self, db_provider: DatabaseConnectionProvider, tasks,
                 io_loop: IOLoop, polling_interval=1800,
                 n_workers=1, sleep_time=0.5, db_flush_limit=15):
        """

        :param db_provider: The input SQLite DB connection where we can query all the places with popular times
        :param polling_interval: the time interval to poll current popularity from  Google, in seconds
        :param n_workers: Number of concurrent workers to scrape Google
        :param sleep_time: Number of seconds to sleep after each scrape by each worker
        """
        self.client = PopularTimesClient()
        self.db_provider = db_provider

        self.progress_bar = None

        self.tasks = tasks
        self.n_workers = n_workers
        self.polling_interval = polling_interval
        self.sleep_time = sleep_time
        self.db_flush_limit = db_flush_limit

        self.db_write_buffer = deque()

        # a run loop where we can schedule events
        self.loop = io_loop
        # the queue where we store all the tasks for each interval-based trigger

        self.task_queue = tornado.queues.Queue()
        # [every 1800s --> put all places into the queue --> [|||||||]
        #                                                     ^    ^
        #                                                     |    |  -- workers pull from the queue

        # a periodic callback to insert all tasks into the queue
        self.producer_callback = PeriodicCallback(lambda: asyncio.create_task(self.producer()),
                                                  # milliseconds
                                                  self.polling_interval * 1000.0)

    # start the scraper
    def start(self):
        # start workers
        for i in range(self.n_workers):
            self.loop.spawn_callback(self.scrape_worker, i + 1)

        # trigger the producer IMMEDIATELY so that we have some tasks to work out when the server starts up;
        self.loop.add_callback(self.producer)

        # start the periodic callback
        self.producer_callback.start()

    def write_to_db(self, timestamp, result, task, force_flush=False):
        # this is the method that we will write to the DB
        # insert the element into the db buffer;
        # if the buffer has more than X elements (where X is self.db_flush_limit), then
        # (1) get the connection from self.db_provider.get_connection
        # (2) get a cursor; call cursor.executemany() to insert X elements into the DB

        if result is not None:
            self.db_write_buffer.append((timestamp, result, task))

        if len(self.db_write_buffer) >= self.db_flush_limit or force_flush:
            # print(f"Flushing to DB (force: {force_flush})")

            conn = self.db_provider.get_connection
            cursor = conn.cursor()

            to_insert_values = [(task.batch_id, r.place_id, ts, r.current_popularity or -1, r.rating_n or 0,
                                 task.id, json.dumps(r))
                                for (ts, r, task) in self.db_write_buffer]
            cursor.executemany('''INSERT INTO curr_popularity VALUES (?, ?, ?, ?, ?, ?, ?)''', to_insert_values)

            conn.commit()

            # clear buffer
            self.db_write_buffer.clear()

    async def producer(self):
        """
        Adding scraping tasks to the task queue
        :return:
        """
        print(f"Enqueuing {len(self.tasks)} tasks into the queue")
        batch_id = int(datetime.strftime(datetime.utcnow(), "%Y%m%d%H%M"))

        for task in self.tasks:
            await self.task_queue.put(replace(task, batch_id=batch_id))

        self.progress_bar = tqdm.tqdm(total=len(self.tasks), desc="Tasks")

    def _complete_task(self):
        self.task_queue.task_done()

        if self.progress_bar is not None:
            self.progress_bar.update(1)

        if self.task_queue.qsize() == 0:
            self.progress_bar.close()

    async def scrape_worker(self, worker_id):
        """
        This is the main worker for scraping Google (by polling tasks from the Queue)
        :return:
        """
        while True:
            is_empty = self.task_queue.qsize() == 1

            task = await self.task_queue.get()
            # print(f"[Worker {worker_id} Got task: {task}")

            result = await self.client.get_popular_times_by_name_addr(task.name, task.address)

            # signify that the task is done
            self._complete_task()

            timestamp = int(datetime.utcnow().timestamp() * 1000)

            # if the task queue is empty, it means that we finish the current batch;
            # force flush to prevent data loss
            self.write_to_db(timestamp, result, task, force_flush=is_empty)

            await gen.sleep(self.sleep_time)


class HttpServer:
    def __init__(self, db_provider: DatabaseConnectionProvider):
        pass


def load_tasks(input_db):
    """
    Return all tasks that have popular times.
    The task should be a Task instance
    :param input_db:
    :return:
    """
    conn = sqlite3.connect(input_db)
    cur = conn.cursor()
    tasks = []
    for row in cur.execute("SELECT id, name, address from task_list"):
        tasks.append(Task(*row))

    conn.close()

    return tasks


def create_table(conn):
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS curr_popularity (batch_id integer, id text,
     timestamp integer, curr_popularity integer, rating_n integer, request_id text, results blob)''')


def main():
    parser = ArgumentParser("Run a periodic popularity scraper using Google unofficial API")
    parser.add_argument("--output-database", required=True, help="The database to store the results")
    parser.add_argument("--input-database", required=True, help="The database to load all the tasks")
    parser.add_argument("--n-workers", type=int, default=1, help="The number of concurrent workers")
    parser.add_argument("--polling-interval", type=int, default=1800,
                        help="The number of seconds between each bulk scrape.")
    parser.add_argument("--sleep-time", type=float, default=0.5,
                        help="The number of seconds to sleep after completing each task.")
    parser.add_argument("--flush-limit", type=int, default=10,
                        help="The max number of results stored in buffer before flushing.")

    args = parser.parse_args()

    db_conn = sqlite3.connect(args.output_database)
    create_table(db_conn)
    db_provider = StaticDatabaseConnectionProvider(db_conn)

    io_loop = IOLoop.current()

    tasks = load_tasks(args.input_database)

    # http_server = HttpServer(db_provider, )
    scraper = PopularTimesScraper(db_provider, tasks, io_loop, n_workers=args.n_workers)
    scraper.start()

    io_loop.start()


if __name__ == "__main__":
    main()
