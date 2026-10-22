import os
import tempfile
import unittest
from unittest import mock

from akf_workshop.box_source.adapter import BoxPlaceholderAdapter
from akf_workshop.box_source.box_api import BoxApiAdapter
from akf_workshop.box_source.source import make_adapter


def group(name):
    return {"status": "accepted", "accessible_by": {"type": "group", "name": name}}


class FakeBox:
    """Box with root 1 -> docs (shared with attendees) and restricted (shared with leads, plus one direct user)."""

    def __init__(self):
        self.downloads = 0
        self.items = {
            "1": [{"type": "folder", "id": "2", "name": "docs"}, {"type": "folder", "id": "3", "name": "restricted"}],
            "2": [self.file("10", "guide.md")],
            "3": [self.file("11", "policy.md"), self.file("12", "scan.png")],
        }
        self.collaborations = {
            ("folders", "2"): [group("workshop-attendees")],
            ("folders", "3"): [group("support-leads")],
            ("files", "11"): [{"status": "accepted", "accessible_by": {"type": "user", "login": "auditor@example.com"}},
                              {"status": "pending", "accessible_by": {"type": "user", "login": "invited@example.com"}}],
        }
        self.contents = {"10": b"# Guide\nhello", "11": b"# Policy\nescalate in 30 minutes", "12": b"\x89PNG\x00\xff"}

    @staticmethod
    def file(file_id, name):
        return {"type": "file", "id": file_id, "name": name, "file_version": {"id": f"9{file_id}"},
                "modified_at": "2026-10-21T10:00:00-07:00", "owned_by": {"login": "service@boxdevedition.com"}}

    def get(self, path, params=None):
        if path == "/folders/1":
            return {"id": "1", "name": "Workshop"}
        kind, item_id, _ = path.strip("/").split("/")
        return {"entries": self.collaborations.get((kind, item_id), [])}

    def paged(self, path, params=None, limit=1000):
        return self.items[path.split("/")[2]]

    def download(self, file_id):
        self.downloads += 1
        return self.contents[file_id]


class BoxApiAdapterTest(unittest.TestCase):
    def setUp(self):
        self.cache = tempfile.TemporaryDirectory()
        mock.patch.dict(os.environ, {"AKF_CACHE_DIR": self.cache.name}).start()
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(self.cache.cleanup)
        self.box = FakeBox()
        self.adapter = BoxApiAdapter("1", client=self.box)

    def by_name(self):
        return {f.name: f for f in self.adapter.list_files()}

    def test_files_carry_box_identity_path_and_labels(self):
        policy = self.by_name()["policy.md"]
        self.assertEqual(policy.file_id, "box-11")
        self.assertEqual(policy.version, "v911")
        self.assertEqual(policy.path, "/Box/Workshop/restricted/policy.md")
        self.assertEqual(policy.labels, ("restricted",))

    def test_permissions_are_inherited_from_folders(self):
        files = self.by_name()
        self.assertEqual(files["guide.md"].acl.groups, ("workshop-attendees",))
        self.assertEqual(files["policy.md"].acl.groups, ("support-leads",))
        self.assertTrue(files["guide.md"].acl.allows("dev@example.com", {"workshop-attendees"}))
        self.assertFalse(files["policy.md"].acl.allows("dev@example.com", {"workshop-attendees"}))

    def test_direct_and_owner_access_but_not_pending_invites(self):
        acl = self.by_name()["policy.md"].acl
        self.assertIn("auditor@example.com", acl.users)
        self.assertIn("service@boxdevedition.com", acl.users)
        self.assertNotIn("invited@example.com", acl.users)

    def test_text_and_binary_content(self):
        files = self.by_name()
        self.assertIn("30 minutes", self.adapter.get_file(files["policy.md"].file_id).content)
        image = self.adapter.get_file(files["scan.png"].file_id)
        self.assertEqual(image.content, "")
        self.assertTrue(image.content_bytes.startswith(b"\x89PNG"))

    def test_content_is_cached_by_version(self):
        file_id = self.by_name()["guide.md"].file_id
        self.adapter.get_file(file_id)
        BoxApiAdapter("1", client=self.box).get_file(file_id)
        self.assertEqual(self.box.downloads, 1)


class MakeAdapterTest(unittest.TestCase):
    def test_local_placeholder_by_default(self):
        with mock.patch.dict(os.environ, {"BOX_FOLDER_ID": ""}):
            self.assertIsInstance(make_adapter("sample_box"), BoxPlaceholderAdapter)

    def test_box_when_folder_id_is_set(self):
        with mock.patch.dict(os.environ, {"BOX_FOLDER_ID": "123"}):
            adapter = make_adapter("sample_box")
        self.assertIsInstance(adapter, BoxApiAdapter)
        self.assertEqual(adapter.folder_id, "123")


if __name__ == "__main__":
    unittest.main()
