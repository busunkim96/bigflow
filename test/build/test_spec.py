import logging
import unittest
import textwrap

from typing import Any, Dict, List
from test import mixins

from unittest import mock

from bigflow.build import spec


class ReadSpecTestCase(
    mixins.TempCwdMixin,
    unittest.TestCase,
):

    def test_should_raise_error_when_cant_find_deployment_config(self):
        # then
        with self.assertRaises(ValueError):
            # when
            spec.get_docker_repository_from_deployment_config(self.cwd / 'unknown.py')

    @mock.patch('bigflow.version.get_version')
    def test_fallback_to_detect_version(self, get_version_mock: mock.Mock):
        # given
        get_version_mock.side_effect = ValueError()

        # when
        with self.assertLogs(level=logging.WARNING) as logs:
            v = spec.secure_get_version()

        # then
        self.assertTrue(len(logs.records))
        self.assertEqual(v, "INVALID")

    def test_docker_repository_not_in_lower_case(self):

        # given
        dc = self.cwd / "deployment_config.py"
        dc.write_text(textwrap.dedent("""
            import bigflow
            deployment_config = bigflow.Config(name='dev', properties={'docker_repository': "Docker_Repository"})
        """))

        # then
        with self.assertRaises(ValueError):
            # when
            spec.get_docker_repository_from_deployment_config(dc)



class _BaseRealProjectTest(
    mixins.SubprocessMixin,
    mixins.PrototypedDirMixin,
    mixins.BigflowInPythonPathMixin,
    mixins.ABCTestCase,
    unittest.TestCase,
):
    __test__ = False

    expected_name: str
    expected_packages: List[str]
    expected_metainfo: Dict[str, Any]

    # TODO: Add more tests.

    def test_read_spec_from_setuppy(self):

        # when
        s = spec.read_project_spec(self.cwd)

        # then
        self.assertEqual(s.project_dir, self.cwd)
        self.assertEqual(s.name, self.expected_name)
        self.assertEqual(s.metainfo, self.expected_metainfo)
        self.assertCountEqual(s.packages, self.expected_packages)


class SpecBigflowV10TestCase(_BaseRealProjectTest):
    __test__ = True
    proto_dir = "bf-projects/bf_simple_v10"

    expected_name = "bf-simple-v10"
    expected_packages = ["simple_v10"]
    expected_metainfo = {}


class SpecBigflowV11TestCase(_BaseRealProjectTest):
    __test__ = True
    proto_dir = "bf-projects/bf_simple_v11"

    expected_name = "bf-simple-v11"
    expected_packages = ["simple_v11"]
    expected_metainfo = dict(
        author="Bigflow UnitTest",
        description="Sample bigflow project",
        url="http://example.org",
    )


class SpecBigflowV12TestCase(_BaseRealProjectTest):
    __test__ = True
    proto_dir = "bf-projects/bf_simple_v12"

    expected_name = "bf-simple-v12"
    expected_packages = ["simple_v12_one", "simple_v12_two"]
    expected_metainfo = dict(
        author="Bigflow UnitTest",
        description="Sample bigflow project",
        url="http://example.org",
    )

