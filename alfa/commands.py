from io import StringIO
from typing import List

import sadisplay
import uvicorn
from ruamel.yaml import YAML


def get_db_docs(models: List) -> str:  # type: ignore [type-arg]
    desc = sadisplay.describe(models)
    docs: str = sadisplay.plantuml(desc)
    docs = docs.replace('@startuml', '```plantuml\n@startuml')
    docs = docs.replace('@enduml', '@enduml\n```')
    return docs


def get_openapi_docs(server: uvicorn.Server) -> str:
    yaml_str = StringIO()
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.dump(server.config.app.openapi(), yaml_str)
    return yaml_str.getvalue()
