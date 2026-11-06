"""Checks the saved-results flow of common/ui_data.py with fake S3 and Athena clients (no AWS).

Run from dashboard/:  python tests/test_saved_results.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("DASHBOARD_MOCK_DIR", None)

from botocore.exceptions import ClientError  # noqa: E402

from common import ui_data  # noqa: E402


class Body:
    def __init__(self, raw):
        self.raw = raw

    def read(self):
        return self.raw


class FakeS3:
    def __init__(self, can_write=True):
        self.objects, self.can_write = {}, can_write

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": Body(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType=None):
        if not self.can_write:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
        self.objects[Key] = Body


class FakeAthena:
    def __init__(self, s3):
        self.s3, self.runs = s3, 0

    def start_query_execution(self, **kw):
        self.runs += 1
        self.s3.objects["athena-results/x/q1.csv"] = b"a,b\n1,x\n2,y\n"
        return {"QueryExecutionId": "q1"}

    def get_query_execution(self, QueryExecutionId):
        return {"QueryExecution": {"Status": {"State": "SUCCEEDED"},
                                   "ResultConfiguration": {"OutputLocation": "s3://bucket/athena-results/x/q1.csv"}}}


def main():
    s3 = FakeS3()
    athena = FakeAthena(s3)
    df, saved = ui_data._athena(athena, s3, "flow", "SELECT 1", "db1", "s3://b/out")
    assert (athena.runs, saved, df["a"].tolist()) == (1, False, [1, 2]), "first view runs Athena"
    key = ui_data.saved_key("db1", "flow", "SELECT 1")
    assert key in s3.objects and key.startswith("athena-results/dashboard-saved/db1/flow-"), key

    df, saved = ui_data._athena(athena, s3, "flow", "SELECT 1", "db1", "s3://b/out")
    assert (athena.runs, saved, df["b"].tolist()) == (1, True, ["x", "y"]), "second view reads the saved file"

    ui_data._athena(athena, s3, "flow", "SELECT 2", "db1", "s3://b/out")
    assert athena.runs == 2, "an edited query runs again"

    ro = FakeS3(can_write=False)
    df, saved = ui_data._athena(FakeAthena(ro), ro, "flow", "SELECT 1", "db1", "s3://b/out")
    assert not saved and len(df) == 2, "no write access still shows the result"
    print("saved-results checks passed")


if __name__ == "__main__":
    main()
