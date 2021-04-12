"""Read and parse bigflow project configuration (setup.py / pyproject.toml)"""

import textwrap
import typing
import logging
import typing
import dataclasses
import toml
import pprint
from pathlib import Path

import setuptools

import bigflow.resources
import bigflow.version

import bigflow.build.pip
import bigflow.build.dev
import bigflow.build.dataflow.dependency_checker

import bigflow.commons as bf_commons


logger = logging.getLogger(__name__)


_ListStr = typing.List[str]

# copied from `distutils.dist.DistributionMetadata`
_PROJECT_METAINFO_KEYS = (
    "name", "version", "author", "author_email",
    "maintainer", "maintainer_email", "url",
    "license", "description", "long_description",
    "keywords", "platforms", "fullname", "contact",
    "contact_email", "classifiers", "download_url",
    # PEP 314
    "provides", "requires", "obsoletes",
)


@dataclasses.dataclass
class BigflowProjectSpec:
    """Parameters of bigflow project."""

    # transients: not part of 'pyproject.toml'
    project_dir: Path

    # Basic setuptools info - required or semi-required
    name: str
    version: str
    packages: _ListStr
    requries: _ListStr

    # Setuptools-speicfic but _patched_ (not replaced) by bigflow
    data_files: typing.List

    # Bigflow-specific information and options
    docker_repository: str
    resources_dir: str
    deployment_config_file: str
    project_requirements_file: str

    # Known package metainformation (author, url, description etc, see _PROJECT_METAINFO_KEYS)
    metainfo: typing.Dict[str, typing.Any]

    # Just bypass any unknow options to 'distutils'
    setuptools: typing.Dict[str, typing.Any]


def parse_project_spec(
    project_dir,
    *,
    name,
    docker_repository=None,
    version=None,
    packages=None,
    data_files=None,
    requries=None,
    deployment_config_file="deployment_config.py",
    project_requirements_file="resources/requirements.txt",
    resources_dir="resources",
    **kwargs,

) -> BigflowProjectSpec:
    """Creates instance of BigflowProjectSpec. Populate defaults, coerce values"""

    logger.info("Prepare bigflow project spec...")

    project_dir = project_dir or Path.cwd()
    name = name.replace("_", "-")  # PEP8 compliant package names

    docker_repository = docker_repository or get_docker_repository_from_deployment_config(deployment_config_file)
    version = version or secure_get_version()
    packages = packages or discover_project_packages(project_dir)
    requries = requries or read_project_requirements(project_requirements_file)
    metainfo = {k: kwargs.pop(k) for k in _PROJECT_METAINFO_KEYS if k in kwargs}

    setuptools = kwargs  # all unknown arguments
    if setuptools:
        logger.info("Found unrecognized build parameters: %s", setuptools)

    logger.info("Bigflow project spec is ready")

    return BigflowProjectSpec(
        name=name,
        project_dir=project_dir,
        docker_repository=docker_repository,
        version=version,
        packages=packages,
        requries=requries,
        data_files=data_files,
        resources_dir=resources_dir,
        project_requirements_file=project_requirements_file,
        deployment_config_file=deployment_config_file,
        metainfo=metainfo,
        setuptools=kwargs,
    )


def render_project_spec(prj: BigflowProjectSpec) -> dict:
    """Convertes project spec into embeddable dict"""
    return {
        'name': prj.name,
        'version': prj.version,
        'packages': prj.packages,
        'requries': prj.requries,
        'docker_repository': prj.docker_repository,
        'deployment_config_file': prj.deployment_config_file,
        'project_requirements_file': prj.project_requirements_file,
        **prj.metainfo,
        **prj.setuptools,
    }


def add_spec_to_pyproject_toml(pyproject_toml: Path, prj: BigflowProjectSpec):
    if pyproject_toml.exists():
        data = toml.load(pyproject_toml)
    else:
        data = {}
    data['bigflow-project'] = render_project_spec(prj)
    pyproject_toml.write_text(toml.dumps(data))



def read_project_spec_pyproject(project_dir, **kwargs):
    """Read project spec from pyproject.toml, allowing to overwrite any options.
    Does *NOT* inspect `setup.py` (as it is intented to be used from setup.py)"""

    data = {}
    data.update(_mabye_read_pyproject(project_dir) or {})
    data.update(kwargs)
    return parse_project_spec(project_dir, **data)


def _mabye_read_pyproject(dir: Path):
    pyproject_toml = dir / "pyproject.toml"
    if pyproject_toml.exists():
        logger.info("Load config %s", pyproject_toml)
        data = toml.load(pyproject_toml)
        return data.get('bigflow-project')


def read_project_spec(dir: Path = None):
    dir = dir or Path.cwd()

    setuppy = dir / "setup.py"
    if setuppy.exists():
        logger.debug("Read project spec from `setup.py` and `pyproject.toml`")
        setuppy_kwargs = bigflow.build.dev.read_setuppy_args(setuppy)
    else:
        logger.debug("Read project spec only from `pyproject.toml`")
        setuppy_kwargs = {}

    try:
        return read_project_spec_pyproject(dir, **setuppy_kwargs)
    except Exception:
        raise ValueError(
            "The project configuration is invalid. "
            "Check the documentation how to create a valid `setup.py`: "
            "https://github.com/allegro/bigflow/blob/master/docs/build.md"
        )


# Provide defaults for project-spec

def discover_project_packages(project_dir):
    ret = setuptools.find_packages(where=project_dir, exclude=["test.*", "test"])
    logger.info(
        "Automatically discovered %d packages: \n%s",
        len(ret),
        "\n".join(map(" - %s".__mod__, ret)),
    )
    return ret


def read_project_requirements(project_requirements_file):
    logger.info("Read project requirements from %s", project_requirements_file)
    req_txt = Path(project_requirements_file)
    recompiled = bigflow.build.pip.maybe_recompile_requirements_file(req_txt)
    if recompiled:
        logger.warning(textwrap.dedent(f"""
            !!! Requirements file was recompiled, you need to reinstall packages.
            !!! Run this command from your virtualenv:
            pip install -r {req_txt}
        """))
    bigflow.build.dataflow.dependency_checker.check_beam_worker_dependencies_conflict(req_txt)  # XXX
    return bigflow.build.pip.read_requirements(req_txt)


def get_docker_repository_from_deployment_config(deployment_config_file: Path) -> str:
    logger.info("Read docker repository from %s", deployment_config_file)

    import bigflow.cli   # TODO: refactor, remove this import
    try:
        config = bigflow.cli.import_deployment_config(str(deployment_config_file), 'docker_repository')
    except ValueError:
        raise ValueError(f"Can't find the specified deployment configuration: {deployment_config_file}")

    if isinstance(config, bigflow.Config):
        config = config.resolve()

    if "docker_repository" in config and not config["docker_repository"].islower():
        raise ValueError("`docker_repository` variable should be in lower case")
    docker_repository = config['docker_repository']

    if docker_repository is None:
        raise ValueError(f"Can't find the 'docker_repository' property in the specified config file: {deployment_config_file}")
    return docker_repository


def secure_get_version() -> str:
    logger.debug("Autodetected project version using git")
    try:
        version = bigflow.version.get_version()
        logger.info("Autodected project version is %s", version)
        return version
    except Exception as e:
        logger.error("Can't get the current package version. To use the automatic versioning, "
                     "you need to use git inside your project directory: %s", e)
        return "INVALID"
