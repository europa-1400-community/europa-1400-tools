from pathlib import Path

from europa1400_tools.cli.common_options import CommonOptions
from europa1400_tools.cli.convert_options import ConvertOptions
from europa1400_tools.construct.ageb import AGeb
from europa1400_tools.construct.base_construct import BaseConstruct
from europa1400_tools.converter.base_converter import BaseConverter


class AGebConverter(BaseConverter):
    """Convert AGeb files."""

    @property
    def decoded_path(self) -> Path:
        return ConvertOptions.instance.decoded_ageb_path

    @property
    def converted_path(self) -> Path:
        return ConvertOptions.instance.converted_ageb_path

    @property
    def is_single_output_file(self) -> bool:
        return True

    def convert(
        self,
        value: AGeb,
        output_path: Path,
    ) -> list[Path]:
        ageb_json = value.to_json()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ageb_json, encoding="utf-8")

        return [output_path]
