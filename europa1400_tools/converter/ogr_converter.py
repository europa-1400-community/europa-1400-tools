from pathlib import Path

from europa1400_tools.cli.common_options import CommonOptions
from europa1400_tools.const import JSON_EXTENSION
from europa1400_tools.construct.base_construct import BaseConstruct
from europa1400_tools.construct.ogr import Ogr
from europa1400_tools.converter.base_converter import BaseConverter


class OgrConverter(BaseConverter):
    """Converter for OGR files."""

    @property
    def decoded_path(self) -> Path:
        return CommonOptions.instance.decoded_groups_path

    @property
    def converted_path(self) -> Path:
        return CommonOptions.instance.converted_groups_path

    @property
    def is_single_output_file(self) -> bool:
        return True

    def convert(
        self,
        value: Ogr,
        output_path: Path,
    ) -> list[Path]:
        value_json = value.to_json()

        json_output_path = (output_path / value.path.name).with_suffix(JSON_EXTENSION)
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(value_json, encoding="utf-8")

        return [json_output_path]
