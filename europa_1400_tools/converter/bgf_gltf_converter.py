import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pygltflib import (
    ANIM_LINEAR,
    ARRAY_BUFFER,
    BLEND,
    ELEMENT_ARRAY_BUFFER,
    FLOAT,
    GLTF2,
    OPAQUE,
    SCALAR,
    UNSIGNED_INT,
    VEC2,
    VEC3,
    WEIGHTS,
    Accessor,
    Animation,
    AnimationChannel,
    AnimationChannelTarget,
    AnimationSampler,
    Attributes,
    Buffer,
    BufferView,
    Image,
    Material,
    Mesh,
    Node,
    PbrMetallicRoughness,
    Primitive,
    Scene,
)
from pygltflib import Texture as GltfTexture
from pygltflib import TextureInfo

from europa_1400_tools.const import (
    GLB_EXTENSION,
    PICKLE_EXTENSION,
    PNG_EXTENSION,
    TargetFormat,
)
from europa_1400_tools.construct.baf import Baf
from europa_1400_tools.construct.bgf import Bgf
from europa_1400_tools.converter.bgf_converter import BgfConverter
from europa_1400_tools.converter.common import Texture
from europa_1400_tools.decoder.commands import decode_animations, decode_objects
from europa_1400_tools.extractor.commands import extract_file
from europa_1400_tools.helpers import (
    bitmap_to_gltf_uri,
    bytes_to_gltf_uri,
    normalize,
    png_to_gltf_uri,
)
from europa_1400_tools.preprocessor.commands import preprocess_animations


@dataclass
class GltfPrimitive:
    """Class representing a primitive in a gLTF file."""

    vertices: np.ndarray
    baf_to_vertices_per_key: list[np.ndarray]
    normals: np.ndarray
    uvs: np.ndarray
    indices: np.ndarray
    texture_index: int
    texture: Texture


@dataclass
class GltfMesh:
    """Class representing a mesh in a gLTF file."""

    name: str
    primitives: list[GltfPrimitive]


class BgfGltfConverter(BgfConverter):
    """Class for converting BGF files to gLTF."""

    def __init__(self, common_options):
        super().__init__(common_options)

        if common_options.target_format != TargetFormat.GLTF_STATIC:
            if (
                self.common_options.mapped_animations_path.exists()
                and common_options.use_cache
            ):
                with open(
                    self.common_options.mapped_animations_path, "rb"
                ) as input_file:
                    self.baf_to_bgfs = pickle.load(input_file)
            else:
                self.extracted_objects_paths = extract_file(
                    self.common_options.game_objects_path,
                    self.common_options.extracted_objects_path,
                )

                self.extracted_animations_paths = extract_file(
                    self.common_options.game_animations_path,
                    self.common_options.extracted_animations_path,
                )

                self.decoded_objects_paths = decode_objects(
                    common_options, self.extracted_objects_paths
                )

                self.decoded_animations_paths = decode_animations(
                    common_options, self.extracted_animations_paths
                )

                self.baf_to_bgfs, _ = preprocess_animations(
                    self.common_options.extracted_objects_path,
                    self.common_options.extracted_animations_path,
                    self.decoded_objects_paths,
                    self.decoded_animations_paths,
                )

    def convert_bgf_file(
        self,
        bgf: Bgf,
        output_path: Path,
        target_format: TargetFormat,
        textures: list[Texture],
    ) -> list[Path]:
        if bgf.name == "gb_GUTSHAUS":
            pass

        reordered_textures = [None] * len(textures)
        missing_textures: list[Texture] = []

        footer_names = [
            bgf_texture.name
            for bgf_texture in bgf.footer.texture_names
            if normalize(bgf_texture.name)
            in [normalize(texture.bgf_texture.name) for texture in textures]
        ]

        normalized_footer_names = [
            normalize(footer_name) for footer_name in footer_names
        ]
        for i, texture in enumerate(textures):
            if normalize(texture.bgf_texture.name) not in normalized_footer_names:
                missing_textures.append(texture)
                continue

            texture_index = normalized_footer_names.index(
                normalize(texture.bgf_texture.name)
            )
            reordered_textures[texture_index] = texture

        reordered_textures = [texture for texture in reordered_textures if texture]
        reordered_textures.extend(missing_textures)
        textures = reordered_textures

        name = bgf.path.stem

        gltf = GLTF2()

        bafs: list[Baf] = []

        if target_format == TargetFormat.GLTF:
            baf_paths = [
                (self.common_options.decoded_animations_path / baf_path).with_suffix(
                    PICKLE_EXTENSION
                )
                for baf_path, bgfs in self.baf_to_bgfs.items()
                if any(bgf_path.stem.lower() == name.lower() for bgf_path in bgfs)
            ]

            for baf_path in baf_paths:
                with open(baf_path, "rb") as input_file:
                    baf = pickle.load(input_file)
                    bafs.append(baf)

        gltf_mesh = self._convert_mesh(bgf, bafs, name, textures)

        scene = Scene(nodes=[0])
        gltf.scenes.append(scene)

        primitives: list[Primitive] = []
        mesh = Mesh(
            primitives=primitives,
        )
        gltf.meshes.append(mesh)

        node = Node(
            mesh=0,
        )
        gltf.nodes.append(node)

        for i, gltf_primitive in enumerate(gltf_mesh.primitives):
            primitive = Primitive(
                attributes={
                    "POSITION": len(gltf.accessors) + 1,
                    "NORMAL": len(gltf.accessors) + 2,
                    "TEXCOORD_0": len(gltf.accessors) + 3,
                },
                indices=len(gltf.accessors),
                material=i,
            )
            primitives.append(primitive)

            self._add_gltf_data(
                gltf=gltf,
                data=gltf_primitive.indices,
                buffer_type=ELEMENT_ARRAY_BUFFER,
                data_type=UNSIGNED_INT,
                data_format=SCALAR,
                name=f"indices_{i}",
                minmax=False,
            )

            self._add_gltf_data(
                gltf=gltf,
                data=gltf_primitive.vertices,
                buffer_type=ARRAY_BUFFER,
                data_type=FLOAT,
                data_format=VEC3,
                name=f"vertices_{i}",
            )

            self._add_gltf_data(
                gltf=gltf,
                data=gltf_primitive.normals,
                buffer_type=ARRAY_BUFFER,
                data_type=FLOAT,
                data_format=VEC3,
                name=f"vertex_normals_{i}",
            )

            self._add_gltf_data(
                gltf=gltf,
                data=gltf_primitive.uvs,
                buffer_type=ARRAY_BUFFER,
                data_type=FLOAT,
                data_format=VEC2,
                name=f"uv_coordinates_{i}",
            )

            if gltf_primitive.texture.main_texture_path.suffix.lower() == PNG_EXTENSION:
                texture_uri = png_to_gltf_uri(gltf_primitive.texture.main_texture_path)
            else:
                texture_uri = bitmap_to_gltf_uri(
                    gltf_primitive.texture.main_texture_path
                )

            gltf.images.append(
                Image(
                    uri=texture_uri,
                )
            )
            gltf.textures.append(
                GltfTexture(
                    source=i,
                    name=gltf_primitive.texture.main_texture_name,
                )
            )
            gltf.materials.append(
                Material(
                    name=gltf_primitive.texture.main_texture_name,
                    pbrMetallicRoughness=PbrMetallicRoughness(
                        baseColorTexture=TextureInfo(
                            index=i,
                        ),
                        metallicFactor=0.0,
                        roughnessFactor=1.0,
                    ),
                    doubleSided=True,
                    alphaMode=BLEND if gltf_primitive.texture.has_alpha else OPAQUE,
                )
            )

            total_vertices_per_key: np.ndarray = (
                np.concatenate(gltf_primitive.baf_to_vertices_per_key)
                if gltf_primitive.baf_to_vertices_per_key
                else np.array([])
            )

            for j, anim_vertices in enumerate(total_vertices_per_key):
                relative_anim_vertices = anim_vertices - gltf_primitive.vertices
                self._add_gltf_data(
                    gltf=gltf,
                    data=relative_anim_vertices,
                    buffer_type=ARRAY_BUFFER,
                    data_type=FLOAT,
                    data_format=VEC3,
                    name=f"vertices_{i}_{j}",
                )

                primitive.targets.append(
                    Attributes(
                        POSITION=len(gltf.accessors) - 1,
                    )
                )

        target_index = 0

        if len(bafs) > 0:
            total_keyframe_count = len(total_vertices_per_key)

            bafs = bafs[:1]
            for baf in bafs:
                keyframe_count = baf.keyframe_count

                weight_values = []
                for i in range(keyframe_count):
                    weight_values.append([0.0] * total_keyframe_count)
                    weight_values[-1][target_index + i] = 1.0

                weight_values_flattened = np.array(
                    weight_values, dtype=np.float32
                ).flatten()

                self._add_gltf_data(
                    gltf=gltf,
                    data=weight_values_flattened,
                    data_type=FLOAT,
                    data_format=SCALAR,
                    name="weight_values",
                    minmax=False,
                )
                weight_values_id = len(gltf.accessors) - 1

                time_values: np.ndarray = np.arange(0, keyframe_count, dtype=np.float32)
                if baf.baf_ini is not None and baf.baf_ini.key_times is not None:
                    time_values = np.array(
                        baf.baf_ini.key_times,
                        dtype=np.float32,
                    )

                self._add_gltf_data(
                    gltf=gltf,
                    data=time_values,
                    data_type=FLOAT,
                    data_format=SCALAR,
                    name="time_values",
                )
                time_values_id = len(gltf.accessors) - 1

                animation = Animation(
                    name=baf.path.stem.lower(),
                    samplers=[
                        AnimationSampler(
                            input=time_values_id,
                            interpolation=ANIM_LINEAR,
                            output=weight_values_id,
                        ),
                    ],
                    channels=[
                        AnimationChannel(
                            sampler=0,
                            target=AnimationChannelTarget(
                                node=0,
                                path=WEIGHTS,
                            ),
                        ),
                    ],
                )
                continue
                gltf.animations.append(animation)

                target_index += keyframe_count

        glb_output_path = output_path / Path(name).with_suffix(GLB_EXTENSION)
        gltf.save_binary(glb_output_path)

        return [glb_output_path]

    def _add_gltf_data(
        self,
        gltf: GLTF2,
        data: np.ndarray,
        data_type: int,
        data_format: str,
        name: str = "",
        minmax: bool = True,
        buffer_type: int | None = None,
    ) -> tuple[Buffer, BufferView, Accessor]:
        data_bytes = data.tobytes()

        data_buffer = Buffer(
            byteLength=len(data_bytes),
            uri=bytes_to_gltf_uri(data_bytes),
            extras={
                "name": name,
            },
        )
        gltf.buffers.append(data_buffer)

        data_buffer_view = BufferView(
            buffer=len(gltf.buffers) - 1,
            byteLength=len(data_bytes),
            byteOffset=0,
            target=buffer_type,
            extras={
                "name": name,
            },
        )
        gltf.bufferViews.append(data_buffer_view)

        min: list[float] | None = None
        max: list[float] | None = None

        if minmax:
            if data.ndim == 1:
                min = [float(np.min(data))]
                max = [float(np.max(data))]
            else:
                min = [float(np.min(data[:, i])) for i in range(data.shape[1])]
                max = [float(np.max(data[:, i])) for i in range(data.shape[1])]

        data_accessor = Accessor(
            bufferView=len(gltf.bufferViews) - 1,
            byteOffset=0,
            componentType=data_type,
            count=len(data),
            type=data_format,
            min=min,
            max=max,
            extras={
                "name": name,
            },
        )
        gltf.accessors.append(data_accessor)

        return data_buffer, data_buffer_view, data_accessor

    def _convert_mesh(
        self, bgf: Bgf, bafs: list[Baf], name: str, textures: list[Texture]
    ) -> Mesh:
        """Convert Bgf to gltf mesh."""

        gltf_primitives: list[GltfPrimitive] = []
        gltf_mesh = GltfMesh(
            name=name,
            primitives=gltf_primitives,
        )

        faces = np.array(
            [
                [
                    polygon.face.a,
                    polygon.face.c,
                    polygon.face.b,
                ]
                for polygon in bgf.mapping_object.polygons
            ],
            dtype=np.uint32,
        )

        texture_indices = np.array(
            [polygon.texture_index for polygon in bgf.mapping_object.polygons],
            dtype=np.uint32,
        )

        vertices = np.array(
            [
                [
                    vertex_mapping.vertex1.x,
                    vertex_mapping.vertex1.y,
                    -vertex_mapping.vertex1.z,
                ]
                for vertex_mapping in bgf.mapping_object.vertex_mappings
            ],
            dtype=np.float32,
        )

        normals = np.array(
            [
                [
                    vertex_mapping.vertex2.x,
                    vertex_mapping.vertex2.y,
                    -vertex_mapping.vertex2.z,
                ]
                for vertex_mapping in bgf.mapping_object.vertex_mappings
            ],
            dtype=np.float32,
        )

        face_uvs = np.array(
            [
                [
                    [
                        polygon.texture_mapping.a.u,
                        polygon.texture_mapping.a.v,
                    ],
                    [
                        polygon.texture_mapping.c.u,
                        polygon.texture_mapping.c.v,
                    ],
                    [
                        polygon.texture_mapping.b.u,
                        polygon.texture_mapping.b.v,
                    ],
                ]
                for polygon in bgf.mapping_object.polygons
            ]
        )

        # baf_to_bgf_vertices_per_key = []
        # for baf in bafs:
        #     bgf_vertices_per_key = baf.get_vertices_per_key()
        #     baf_to_bgf_vertices_per_key.append(bgf_vertices_per_key)

        for texture_index in range(len(textures)):
            primitive = self.calculate_primitive(
                faces,
                texture_indices,
                vertices,
                normals,
                face_uvs,
                texture_index,
                textures[texture_index],
            )

            if primitive is not None:
                gltf_primitives.append(primitive)

        return gltf_mesh

    def calculate_primitive(
        self,
        faces: np.ndarray,
        texture_indices: np.ndarray,
        vertices: np.ndarray,
        normals: np.ndarray,
        face_uvs: np.ndarray,
        texture_index: int,
        texture: Texture,
    ) -> GltfPrimitive | None:
        # each texture also has its own animation vertices
        # vertices_per_key_per_anim = []
        # for bgf_vertices_per_key in baf_to_bgf_vertices_per_key:
        #     vertices_per_key = np.empty_like(bgf_vertices_per_key, dtype=np.float32)
        #     vertices_per_key_per_anim.append(vertices_per_key)

        selected_faces = faces[texture_indices == texture_index]
        selected_face_uvs = face_uvs[texture_indices == texture_index]

        if len(selected_faces) == 0 or len(selected_face_uvs) == 0:
            return None

        primitive_indices: list = []
        primitive_face_uvs: list = []
        primitive_vertices: list = []
        primitive_normals: list = []

        vertex_dict = {}

        for selected_face, selected_face_uvs in zip(selected_faces, selected_face_uvs):
            for selected_face_vertex_index, selected_face_uv in zip(
                selected_face, selected_face_uvs
            ):
                selected_face_u = selected_face_uv[0]
                selected_face_v = selected_face_uv[1]

                key = (selected_face_vertex_index, selected_face_u, selected_face_v)

                if key not in vertex_dict:
                    primitive_index = len(primitive_vertices)
                    vertex_dict[key] = primitive_index

                    vertex = vertices[selected_face_vertex_index]
                    normal = normals[selected_face_vertex_index]

                    primitive_vertices.append(vertex)
                    primitive_normals.append(normal)
                    primitive_face_uvs.append(selected_face_uv)

                    # for bgf_vertices_per_key, vertices_per_key in zip(
                    #     baf_to_bgf_vertices_per_key, vertices_per_key_per_anim
                    # ):
                    #     for keyframe in range(bgf_vertices_per_key.shape[0]):
                    #         vertex_per_key = bgf_vertices_per_key[keyframe][
                    #             vertex_index
                    #         ]
                    #         vertices_per_key = np.append(
                    #             vertices_per_key, vertex_per_key
                    #         )

                primitive_indices.append(vertex_dict[key])

        primitive_indices_np = np.array(primitive_indices, dtype=np.uint32)
        primitive_uvs_np = np.array(primitive_face_uvs, dtype=np.float32)
        primitive_normals_np = np.array(primitive_normals, dtype=np.float32)
        primitive_vertices_np = np.array(primitive_vertices, dtype=np.float32)

        # for vertices_per_key in vertices_per_key_per_anim:
        #     vertices_per_key = np.array(vertices_per_key, dtype=np.float32)

        gltf_primitive = GltfPrimitive(
            indices=primitive_indices_np,
            vertices=primitive_vertices_np,
            # baf_to_vertices_per_key=vertices_per_key_per_anim,
            baf_to_vertices_per_key=[],
            normals=primitive_normals_np,
            uvs=primitive_uvs_np,
            texture_index=texture_index,
            texture=texture,
        )

        return gltf_primitive
