import os
import unittest
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from wifimon.collector import (
    ClientInfo,
    RemoteCollector,
    _parse_station_dump,
)
from wifimon.detector import Detector
from wifimon.storage import Storage


class PostgresTestCase(unittest.TestCase):
    def setUp(self):
        load_dotenv()
        self.database_url = self._without_schema_option(os.environ["DATABASE_URL"])
        self.schema = f"wifimon_test_{uuid4().hex}"
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema))
            )
        self.storage_url = self._url_with_search_path(self.database_url, self.schema)
        self.storage = Storage(self.storage_url)

    def tearDown(self):
        self.storage.close()
        with psycopg.connect(self.database_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema))
            )

    @staticmethod
    def _url_with_search_path(database_url, schema):
        database_url = PostgresTestCase._without_schema_option(database_url)
        parsed = urlsplit(database_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["options"] = f"-csearch_path={schema}"
        return urlunsplit(parsed._replace(query=urlencode(query)))

    @staticmethod
    def _without_schema_option(database_url):
        parsed = urlsplit(database_url)
        query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "schema"
        ]
        netloc = parsed.netloc
        if parsed.hostname == "localhost":
            userinfo = netloc.rpartition("@")[0]
            userinfo = f"{userinfo}@" if userinfo else ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{userinfo}127.0.0.1{port}"
        return urlunsplit(parsed._replace(netloc=netloc, query=urlencode(query)))


class StationDumpTests(unittest.TestCase):
    def test_parses_stations_and_estimates_association_time(self):
        now = datetime(2026, 10, 17, 0, 0, 0, tzinfo=timezone.utc)
        output = """Station AA:BB:CC:DD:EE:FF (on wlan0)
        inactive time: 12 ms
        connected time: 90 seconds
Station 11:22:33:44:55:66 (on wlan0)
        inactive time: 20 ms
"""

        stations = _parse_station_dump(output, now)

        self.assertEqual(stations[0]["mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(stations[0]["connected_since"], "2026-10-16T23:58:30+00:00")
        self.assertEqual(stations[1]["mac"], "11:22:33:44:55:66")
        self.assertEqual(stations[1]["connected_since"], "")

    def test_collector_uses_ap_station_list_as_authoritative_source(self):
        collector = RemoteCollector(
            Mock(),
            {"ap_interface": "wlan0", "bridge": "br-lab", "ssid_map": {}},
        )
        collector._run_collection_command = Mock(
            side_effect=[
                (
                    True,
                    "Station aa:bb:cc:dd:ee:ff (on wlan0)\n"
                    "        connected time: 15 seconds",
                ),
                (True, "Interface wlan0\n\ttype AP\n\tssid WifiMon-Lab"),
            ]
        )
        collector.collect_leases = Mock(
            return_value=[
                {
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "ip": "10.20.0.101",
                    "hostname": "lab-client",
                },
                {"mac": "11:22:33:44:55:66", "ip": "10.20.0.102"},
            ]
        )
        collector.collect_arp = Mock(return_value=[])
        collector.collect_namespaces = Mock(return_value=[])
        collector.collect_fdb = Mock(return_value=[])

        result = collector.collect_all()

        self.assertTrue(result.station_scan_ok)
        self.assertEqual(len(result.clients), 1)
        self.assertEqual(result.clients[0].ip, "10.20.0.101")
        self.assertEqual(result.clients[0].hostname, "lab-client")
        self.assertEqual(result.clients[0].ssid, "WifiMon-Lab")
        self.assertEqual(result.clients[0].source, "ap_station")

    def test_failed_ap_station_query_marks_snapshot_untrusted(self):
        collector = RemoteCollector(Mock(), {"ap_interface": "wlan0"})
        collector._run_collection_command = Mock(
            return_value=(False, "")
        )
        collector.collect_leases = Mock()

        result = collector.collect_all()

        self.assertFalse(result.station_scan_ok)
        self.assertEqual(result.clients, [])
        collector.collect_leases.assert_not_called()

    def test_sudo_password_is_sent_over_stdin(self):
        ssh = Mock()
        stdin = Mock()
        stdin.channel = Mock()
        stdout = Mock()
        stdout.read.return_value = b""
        stdout.channel.recv_exit_status.return_value = 0
        stderr = Mock()
        stderr.read.return_value = b""
        stderr.channel.recv_exit_status.return_value = 0
        ssh.exec_command.return_value = (stdin, stdout, stderr)
        collector = RemoteCollector(ssh, {"ssh": {"password": "not-in-command"}})

        collector.run_cmd("iw dev wlan0 station dump", sudo=True)

        command = ssh.exec_command.call_args.args[0]
        self.assertNotIn("not-in-command", command)
        stdin.write.assert_called_once_with("not-in-command\n")
        stdin.channel.shutdown_write.assert_called_once()


class DetectorTests(PostgresTestCase):
    def setUp(self):
        super().setUp()

    @staticmethod
    def client(mac):
        return ClientInfo(
            mac=mac,
            ip="10.20.0.100",
            ssid="WifiMon-Lab",
            connected_since="2026-10-16T23:58:30+00:00",
            last_seen="2026-10-17T00:00:00+00:00",
            source="ap_station",
        )

    def test_ignores_unconfirmed_snapshot_without_changing_state(self):
        detector = Detector(self.storage, {"client_threshold": 5})
        detector.detect([self.client("aa:bb:cc:dd:ee:ff")])

        events = detector.detect([], authoritative=False)

        self.assertEqual(events, [])
        self.assertEqual(
            self.storage.get_client_by_mac("aa:bb:cc:dd:ee:ff")["state"],
            "connected",
        )
        self.assertEqual(len(self.storage.get_scan_history()), 1)

    def test_requires_two_authoritative_misses_to_disconnect(self):
        detector = Detector(
            self.storage,
            {"client_threshold": 5, "disconnect_missed_scans": 2},
        )
        mac = "aa:bb:cc:dd:ee:ff"
        detector.detect([self.client(mac)])

        first_miss = detector.detect([])
        self.assertNotIn("client_disconnected", [event.event_type for event in first_miss])
        self.assertEqual(self.storage.get_client_by_mac(mac)["state"], "stale")

        second_miss = detector.detect([])
        self.assertIn("client_disconnected", [event.event_type for event in second_miss])
        self.assertEqual(self.storage.get_client_by_mac(mac)["state"], "disconnected")

    def test_threshold_alerts_only_on_crossing_and_recovery(self):
        detector = Detector(self.storage, {"client_threshold": 1})
        clients = [self.client("aa:bb:cc:dd:ee:ff"), self.client("11:22:33:44:55:66")]

        first_scan = detector.detect(clients)
        repeated_scan = detector.detect(clients)
        recovered_scan = detector.detect(clients[:1])

        self.assertIn("threshold_exceeded", [event.event_type for event in first_scan])
        self.assertNotIn(
            "threshold_exceeded", [event.event_type for event in repeated_scan]
        )
        self.assertIn(
            "threshold_recovered", [event.event_type for event in recovered_scan]
        )


class StorageMigrationTests(unittest.TestCase):
    def test_adds_new_client_columns_to_existing_database(self):
        load_dotenv()
        database_url = PostgresTestCase._without_schema_option(
            os.environ["DATABASE_URL"]
        )
        schema = f"wifimon_test_{uuid4().hex}"
        with psycopg.connect(database_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
            )
        isolated_url = PostgresTestCase._url_with_search_path(database_url, schema)
        try:
            with psycopg.connect(isolated_url) as connection:
                connection.execute(
                    """
                    CREATE TABLE clients (
                        mac TEXT PRIMARY KEY,
                        ip TEXT DEFAULT '',
                        hostname TEXT DEFAULT '',
                        ssid TEXT DEFAULT '',
                        namespace TEXT DEFAULT '',
                        first_seen TEXT DEFAULT '',
                        last_seen TEXT DEFAULT '',
                        state TEXT DEFAULT 'connected'
                    )
                    """
                )
            storage = Storage(isolated_url)
            storage.upsert_client(
                ClientInfo(
                    mac="aa:bb:cc:dd:ee:ff",
                    connected_since="2026-10-16T23:58:30+00:00",
                    last_seen="2026-10-17T00:00:00+00:00",
                    source="ap_station",
                )
            )
            migrated_client = storage.get_client_by_mac("aa:bb:cc:dd:ee:ff")
            columns = {
                row["column_name"]
                for row in storage.conn.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name = 'clients'",
                    (schema,),
                )
            }
            storage.close()
        finally:
            with psycopg.connect(database_url, autocommit=True) as connection:
                connection.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
                )
        self.assertTrue(
            {"connected_since", "source", "missed_scans"}.issubset(columns)
        )
        self.assertEqual(migrated_client["source"], "ap_station")
        self.assertEqual(
            migrated_client["connected_since"], "2026-10-16T23:58:30+00:00"
        )


if __name__ == "__main__":
    unittest.main()
