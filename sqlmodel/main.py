import ipaddress
import uuid
import weakref
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Annotated,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    overload,
)

from pydantic import BaseModel, EmailStr
from pydantic.fields import FieldInfo as PydanticFieldInfo
from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Interval,
    Numeric,
    Table,
    inspect,
)
from sqlalchemy import Enum as sa_Enum
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import (
    ColumnProperty,
    Mapped,
    RelationshipProperty,
    declared_attr,
    registry,
    relationship,
)
from sqlalchemy.orm.attributes import set_attribute
from sqlalchemy.orm.decl_api import DeclarativeMeta
from sqlalchemy.orm.instrumentation import is_instrumented
from sqlalchemy.orm.properties import MappedSQLExpression
from sqlalchemy.sql.schema import MetaData
from sqlalchemy.sql.sqltypes import LargeBinary, Time, Uuid
from typing_extensions import Literal, TypeAlias, deprecated, get_origin

from ._compat import (  # type: ignore[attr-defined]
    IS_PYDANTIC_V2,
    PYDANTIC_VERSION,
    BaseConfig,
    ModelField,
    ModelMetaclass,
    Representation,
    SQLModelConfig,
    Undefined,
    UndefinedType,
    _calculate_keys,
    finish_init,
    get_annotations,
    get_config_value,
    get_field_metadata,
    get_model_fields,
    get_relationship_to,
    get_sa_type_from_field,
    init_pydantic_private_attrs,
    is_field_noneable,
    is_table_model_class,
    post_init_field_info,
    set_config_value,
    sqlmodel_init,
    sqlmodel_validate,
)
from .sql.sqltypes import AutoString

if TYPE_CHECKING:
    from pydantic._internal._model_construction import ModelMetaclass as ModelMetaclass
    from pydantic._internal._repr import Representation as Representation
    from pydantic_core import PydanticUndefined as Undefined
    from pydantic_core import PydanticUndefinedType as UndefinedType

_T = TypeVar("_T")
NoArgAnyCallable = Callable[[], Any]
IncEx: TypeAlias = Union[
    Set[int],
    Set[str],
    Mapping[int, Union["IncEx", Literal[True]]],
    Mapping[str, Union["IncEx", Literal[True]]],
]
OnDeleteType = Literal["CASCADE", "SET NULL", "RESTRICT"]
SQLAlchemyConstruct = Union[
    hybrid_property,
    hybrid_method,
    ColumnProperty,
    declared_attr,
]


def __dataclass_transform__(
    *,
    eq_default: bool = True,
    order_default: bool = False,
    kw_only_default: bool = False,
    field_descriptors: Tuple[Union[type, Callable[..., Any]], ...] = (()),
) -> Callable[[_T], _T]:
    return lambda a: a


class FieldInfo(PydanticFieldInfo):
    def __init__(self, default: Any = Undefined, **kwargs: Any) -> None:
        primary_key = kwargs.pop("primary_key", False)
        nullable = kwargs.pop("nullable", Undefined)
        foreign_key = kwargs.pop("foreign_key", Undefined)
        ondelete = kwargs.pop("ondelete", Undefined)
        unique = kwargs.pop("unique", False)
        index = kwargs.pop("index", Undefined)
        sa_type = kwargs.pop("sa_type", Undefined)
        sa_column = kwargs.pop("sa_column", Undefined)
        sa_column_args = kwargs.pop("sa_column_args", Undefined)
        sa_column_kwargs = kwargs.pop("sa_column_kwargs", Undefined)
        if sa_column is not Undefined:
            if sa_column_args is not Undefined:
                raise RuntimeError(
                    "Passing sa_column_args is not supported when "
                    "also passing a sa_column"
                )
            if sa_column_kwargs is not Undefined:
                raise RuntimeError(
                    "Passing sa_column_kwargs is not supported when "
                    "also passing a sa_column"
                )
            if primary_key is not Undefined:
                raise RuntimeError(
                    "Passing primary_key is not supported when "
                    "also passing a sa_column"
                )
            if nullable is not Undefined:
                raise RuntimeError(
                    "Passing nullable is not supported when also passing a sa_column"
                )
            if foreign_key is not Undefined:
                raise RuntimeError(
                    "Passing foreign_key is not supported when "
                    "also passing a sa_column"
                )
            if ondelete is not Undefined:
                raise RuntimeError(
                    "Passing ondelete is not supported when also passing a sa_column"
                )
            if unique is not Undefined:
                raise RuntimeError(
                    "Passing unique is not supported when also passing a sa_column"
                )
            if index is not Undefined:
                raise RuntimeError(
                    "Passing index is not supported when also passing a sa_column"
                )
            if sa_type is not Undefined:
                raise RuntimeError(
                    "Passing sa_type is not supported when also passing a sa_column"
                )
        if ondelete is not Undefined:
            if foreign_key is Undefined:
                raise RuntimeError("ondelete can only be used with foreign_key")
        super().__init__(default=default, **kwargs)
        self.primary_key = primary_key
        self.nullable = nullable
        self.foreign_key = foreign_key
        self.ondelete = ondelete
        self.unique = unique
        self.index = index
        self.sa_type = sa_type
        self.sa_column = sa_column
        self.sa_column_args = sa_column_args
        self.sa_column_kwargs = sa_column_kwargs


class RelationshipInfo(Representation):
    def __init__(
        self,
        *,
        back_populates: Optional[str] = None,
        cascade_delete: Optional[bool] = False,
        passive_deletes: Optional[Union[bool, Literal["all"]]] = False,
        link_model: Optional[Any] = None,
        sa_relationship: Optional[RelationshipProperty] = None,  # type: ignore
        sa_relationship_args: Optional[Sequence[Any]] = None,
        sa_relationship_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if sa_relationship is not None:
            if sa_relationship_args is not None:
                raise RuntimeError(
                    "Passing sa_relationship_args is not supported when "
                    "also passing a sa_relationship"
                )
            if sa_relationship_kwargs is not None:
                raise RuntimeError(
                    "Passing sa_relationship_kwargs is not supported when "
                    "also passing a sa_relationship"
                )
        self.back_populates = back_populates
        self.cascade_delete = cascade_delete
        self.passive_deletes = passive_deletes
        self.link_model = link_model
        self.sa_relationship = sa_relationship
        self.sa_relationship_args = sa_relationship_args
        self.sa_relationship_kwargs = sa_relationship_kwargs


# include sa_type, sa_column_args, sa_column_kwargs
@overload
def Field(
    default: Any = Undefined,
    *,
    default_factory: Optional[NoArgAnyCallable] = None,
    alias: Optional[str] = None,
    validation_alias: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    exclude: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    include: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    const: Optional[bool] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    multiple_of: Optional[float] = None,
    max_digits: Optional[int] = None,
    decimal_places: Optional[int] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique_items: Optional[bool] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    allow_mutation: bool = True,
    regex: Optional[str] = None,
    discriminator: Optional[str] = None,
    repr: bool = True,
    primary_key: Union[bool, UndefinedType] = Undefined,
    foreign_key: Any = Undefined,
    unique: Union[bool, UndefinedType] = Undefined,
    nullable: Union[bool, UndefinedType] = Undefined,
    index: Union[bool, UndefinedType] = Undefined,
    sa_type: Union[Type[Any], UndefinedType] = Undefined,
    sa_column_args: Union[Sequence[Any], UndefinedType] = Undefined,
    sa_column_kwargs: Union[Mapping[str, Any], UndefinedType] = Undefined,
    schema_extra: Optional[Dict[str, Any]] = None,
) -> Any: ...


# When foreign_key is str, include ondelete
# include sa_type, sa_column_args, sa_column_kwargs
@overload
def Field(
    default: Any = Undefined,
    *,
    default_factory: Optional[NoArgAnyCallable] = None,
    alias: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    exclude: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    include: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    const: Optional[bool] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    multiple_of: Optional[float] = None,
    max_digits: Optional[int] = None,
    decimal_places: Optional[int] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique_items: Optional[bool] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    allow_mutation: bool = True,
    regex: Optional[str] = None,
    discriminator: Optional[str] = None,
    repr: bool = True,
    primary_key: Union[bool, UndefinedType] = Undefined,
    foreign_key: str,
    ondelete: Union[OnDeleteType, UndefinedType] = Undefined,
    unique: Union[bool, UndefinedType] = Undefined,
    nullable: Union[bool, UndefinedType] = Undefined,
    index: Union[bool, UndefinedType] = Undefined,
    sa_type: Union[Type[Any], UndefinedType] = Undefined,
    sa_column_args: Union[Sequence[Any], UndefinedType] = Undefined,
    sa_column_kwargs: Union[Mapping[str, Any], UndefinedType] = Undefined,
    schema_extra: Optional[Dict[str, Any]] = None,
) -> Any: ...


# Include sa_column, don't include
# primary_key
# foreign_key
# ondelete
# unique
# nullable
# index
# sa_type
# sa_column_args
# sa_column_kwargs
@overload
def Field(
    default: Any = Undefined,
    *,
    default_factory: Optional[NoArgAnyCallable] = None,
    alias: Optional[str] = None,
    validation_alias: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    exclude: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    include: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    const: Optional[bool] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    multiple_of: Optional[float] = None,
    max_digits: Optional[int] = None,
    decimal_places: Optional[int] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique_items: Optional[bool] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    allow_mutation: bool = True,
    regex: Optional[str] = None,
    discriminator: Optional[str] = None,
    repr: bool = True,
    sa_column: Union[Column, UndefinedType, MappedSQLExpression[Any]] = Undefined,
    schema_extra: Optional[Dict[str, Any]] = None,
) -> Any: ...


def Field(
    default: Any = Undefined,
    *,
    default_factory: Optional[NoArgAnyCallable] = None,
    alias: Optional[str] = None,
    validation_alias: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    exclude: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    include: Union[
        AbstractSet[Union[int, str]], Mapping[Union[int, str], Any], Any
    ] = None,
    const: Optional[bool] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    multiple_of: Optional[float] = None,
    max_digits: Optional[int] = None,
    decimal_places: Optional[int] = None,
    min_items: Optional[int] = None,
    max_items: Optional[int] = None,
    unique_items: Optional[bool] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    allow_mutation: bool = True,
    regex: Optional[str] = None,
    discriminator: Optional[str] = None,
    repr: bool = True,
    primary_key: Union[bool, UndefinedType] = Undefined,
    foreign_key: Any = Undefined,
    ondelete: Union[OnDeleteType, UndefinedType] = Undefined,
    unique: Union[bool, UndefinedType] = Undefined,
    nullable: Union[bool, UndefinedType] = Undefined,
    index: Union[bool, UndefinedType] = Undefined,
    sa_type: Union[Type[Any], UndefinedType] = Undefined,
    sa_column: Union[Column, UndefinedType, MappedSQLExpression[Any]] = Undefined,
    sa_column_args: Union[Sequence[Any], UndefinedType] = Undefined,
    sa_column_kwargs: Union[Mapping[str, Any], UndefinedType] = Undefined,
    schema_extra: Optional[Dict[str, Any]] = None,
) -> Any:
    current_schema_extra = schema_extra or {}
    field_info = FieldInfo(
        default,
        default_factory=default_factory,
        alias=alias,
        validation_alias=validation_alias,
        title=title,
        description=description,
        exclude=exclude,
        include=include,
        const=const,
        gt=gt,
        ge=ge,
        lt=lt,
        le=le,
        multiple_of=multiple_of,
        max_digits=max_digits,
        decimal_places=decimal_places,
        min_items=min_items,
        max_items=max_items,
        unique_items=unique_items,
        min_length=min_length,
        max_length=max_length,
        allow_mutation=allow_mutation,
        regex=regex,
        discriminator=discriminator,
        repr=repr,
        primary_key=primary_key,
        foreign_key=foreign_key,
        ondelete=ondelete,
        unique=unique,
        nullable=nullable,
        index=index,
        sa_type=sa_type,
        sa_column=sa_column,
        sa_column_args=sa_column_args,
        sa_column_kwargs=sa_column_kwargs,
        **current_schema_extra,
    )
    post_init_field_info(field_info)
    return field_info


@overload
def Relationship(
    *,
    back_populates: Optional[str] = None,
    cascade_delete: Optional[bool] = False,
    passive_deletes: Optional[Union[bool, Literal["all"]]] = False,
    link_model: Optional[Any] = None,
    sa_relationship_args: Optional[Sequence[Any]] = None,
    sa_relationship_kwargs: Optional[Mapping[str, Any]] = None,
) -> Any: ...


@overload
def Relationship(
    *,
    back_populates: Optional[str] = None,
    cascade_delete: Optional[bool] = False,
    passive_deletes: Optional[Union[bool, Literal["all"]]] = False,
    link_model: Optional[Any] = None,
    sa_relationship: Optional[RelationshipProperty[Any]] = None,
) -> Any: ...


def Relationship(
    *,
    back_populates: Optional[str] = None,
    cascade_delete: Optional[bool] = False,
    passive_deletes: Optional[Union[bool, Literal["all"]]] = False,
    link_model: Optional[Any] = None,
    sa_relationship: Optional[RelationshipProperty[Any]] = None,
    sa_relationship_args: Optional[Sequence[Any]] = None,
    sa_relationship_kwargs: Optional[Mapping[str, Any]] = None,
) -> Any:
    relationship_info = RelationshipInfo(
        back_populates=back_populates,
        cascade_delete=cascade_delete,
        passive_deletes=passive_deletes,
        link_model=link_model,
        sa_relationship=sa_relationship,
        sa_relationship_args=sa_relationship_args,
        sa_relationship_kwargs=sa_relationship_kwargs,
    )
    return relationship_info


@__dataclass_transform__(kw_only_default=True, field_descriptors=(Field, FieldInfo))
class SQLModelMetaclass(ModelMetaclass, DeclarativeMeta):
    __sqlmodel_relationships__: Dict[str, RelationshipInfo]
    __sqlalchemy_constructs__: Dict[str, SQLAlchemyConstruct]
    __sqlalchemy_association_proxies__: Dict[str, AssociationProxy]
    model_config: SQLModelConfig
    model_fields: Dict[str, FieldInfo]
    __config__: Type[SQLModelConfig]
    __fields__: Dict[str, ModelField]  # type: ignore[assignment]
    __table__: Table

    # Replicate SQLAlchemy
    def __setattr__(cls, name: str, value: Any) -> None:
        if is_table_model_class(cls):
            DeclarativeMeta.__setattr__(cls, name, value)
        else:
            super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        if is_table_model_class(cls):
            DeclarativeMeta.__delattr__(cls, name)
        else:
            super().__delattr__(name)

    # From Pydantic
    def __new__(
        cls,
        name: str,
        bases: Tuple[Type[Any], ...],
        class_dict: Dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        relationships: Dict[str, RelationshipInfo] = {}
        sqlalchemy_constructs: Dict[str, SQLAlchemyConstruct] = {}
        sqlalchemy_association_proxies: Dict[str, AssociationProxy] = {}
        dict_for_pydantic = {}
        original_annotations = get_annotations(class_dict)
        pydantic_annotations = {}
        relationship_annotations = {}
        for k, v in class_dict.items():
            if isinstance(v, AssociationProxy):
                sqlalchemy_association_proxies[k] = v
            if isinstance(v, RelationshipInfo):
                relationships[k] = v
            elif isinstance(
                v,
                (
                    hybrid_property,
                    hybrid_method,
                    ColumnProperty,
                    declared_attr,
                    AssociationProxy,
                ),
            ):
                sqlalchemy_constructs[k] = v
            else:
                dict_for_pydantic[k] = v
        for k, v in original_annotations.items():
            if k in relationships:
                relationship_annotations[k] = v
            else:
                pydantic_annotations[k] = v
        dict_used = {
            **dict_for_pydantic,
            "__weakref__": None,
            "__sqlmodel_relationships__": relationships,
            "__annotations__": pydantic_annotations,
            "__sqlalchemy_constructs__": sqlalchemy_constructs,
            "__sqlalchemy_association_proxies__": sqlalchemy_association_proxies,
        }
        # Duplicate logic from Pydantic to filter config kwargs because if they are
        # passed directly including the registry Pydantic will pass them over to the
        # superclass causing an error
        allowed_config_kwargs: Set[str] = {
            key
            for key in dir(BaseConfig)
            if not (
                key.startswith("__") and key.endswith("__")
            )  # skip dunder methods and attributes
        }
        config_kwargs = {
            key: kwargs[key] for key in kwargs.keys() & allowed_config_kwargs
        }
        new_cls = super().__new__(cls, name, bases, dict_used, **config_kwargs)
        new_cls.__annotations__ = {
            **relationship_annotations,
            **pydantic_annotations,
            **new_cls.__annotations__,
        }

        # We did not provide the sqlalchemy constructs to Pydantic's new function above
        # so that they wouldn't be modified. Instead we set them directly to the class below:
        for k, v in sqlalchemy_constructs.items():
            setattr(new_cls, k, v)

        for k, v in sqlalchemy_association_proxies.items():
            setattr(new_cls, k, v)

        def get_config(name: str) -> Any:
            config_class_value = get_config_value(
                model=new_cls, parameter=name, default=Undefined
            )
            if config_class_value is not Undefined:
                return config_class_value
            kwarg_value = kwargs.get(name, Undefined)
            if kwarg_value is not Undefined:
                return kwarg_value
            return Undefined

        config_table = get_config("table")
        if config_table is True:
            # If it was passed by kwargs, ensure it's also set in config
            set_config_value(model=new_cls, parameter="table", value=config_table)
            for k, v in get_model_fields(new_cls).items():
                if k in sqlalchemy_constructs:
                    continue
                col = get_column_from_field(v)
                setattr(new_cls, k, col)
            # Set a config flag to tell FastAPI that this should be read with a field
            # in orm_mode instead of preemptively converting it to a dict.
            # This could be done by reading new_cls.model_config['table'] in FastAPI, but
            # that's very specific about SQLModel, so let's have another config that
            # other future tools based on Pydantic can use.
            set_config_value(
                model=new_cls, parameter="read_from_attributes", value=True
            )
            # For compatibility with older versions
            # TODO: remove this in the future
            set_config_value(model=new_cls, parameter="read_with_orm_mode", value=True)

        config_registry = get_config("registry")
        if config_registry is not Undefined:
            config_registry = cast(registry, config_registry)
            # If it was passed by kwargs, ensure it's also set in config
            set_config_value(model=new_cls, parameter="registry", value=config_table)
            setattr(new_cls, "_sa_registry", config_registry)  # noqa: B010
            setattr(new_cls, "metadata", config_registry.metadata)  # noqa: B010
            setattr(new_cls, "__abstract__", True)  # noqa: B010
            setattr(new_cls, "__pydantic_private__", {})  # noqa: B010
            setattr(new_cls, "__pydantic_extra__", {})  # noqa: B010

        return new_cls

    # Override SQLAlchemy, allow both SQLAlchemy and plain Pydantic models
    def __init__(
        cls, classname: str, bases: Tuple[type, ...], dict_: Dict[str, Any], **kw: Any
    ) -> None:
        # Only one of the base classes (or the current one) should be a table model
        # this allows FastAPI cloning a SQLModel for the response_model without
        # trying to create a new SQLAlchemy, for a new table, with the same name, that
        # triggers an error
        base_is_table = any(is_table_model_class(base) for base in bases)
        if is_table_model_class(cls) and not base_is_table:
            for (
                association_proxy_name,
                association_proxy,
            ) in cls.__sqlalchemy_association_proxies__.items():
                setattr(cls, association_proxy_name, association_proxy)

            for rel_name, rel_info in cls.__sqlmodel_relationships__.items():
                if rel_info.sa_relationship:
                    # There's a SQLAlchemy relationship declared, that takes precedence
                    # over anything else, use that and continue with the next attribute
                    setattr(cls, rel_name, rel_info.sa_relationship)  # Fix #315
                    continue
                raw_ann = cls.__annotations__[rel_name]
                origin = get_origin(raw_ann)
                if origin is Mapped:
                    ann = raw_ann.__args__[0]
                else:
                    ann = raw_ann
                    # Plain forward references, for models not yet defined, are not
                    # handled well by SQLAlchemy without Mapped, so, wrap the
                    # annotations in Mapped here
                    cls.__annotations__[rel_name] = Mapped[ann]  # type: ignore[valid-type]
                relationship_to = get_relationship_to(
                    name=rel_name, rel_info=rel_info, annotation=ann
                )
                rel_kwargs: Dict[str, Any] = {}
                if rel_info.back_populates:
                    rel_kwargs["back_populates"] = rel_info.back_populates
                if rel_info.cascade_delete:
                    rel_kwargs["cascade"] = "all, delete-orphan"
                if rel_info.passive_deletes:
                    rel_kwargs["passive_deletes"] = rel_info.passive_deletes
                if rel_info.link_model:
                    ins = inspect(rel_info.link_model)
                    local_table = getattr(ins, "local_table")  # noqa: B009
                    if local_table is None:
                        raise RuntimeError(
                            "Couldn't find the secondary table for "
                            f"model {rel_info.link_model}"
                        )
                    rel_kwargs["secondary"] = local_table
                rel_args: List[Any] = []
                if rel_info.sa_relationship_args:
                    rel_args.extend(rel_info.sa_relationship_args)
                if rel_info.sa_relationship_kwargs:
                    rel_kwargs.update(rel_info.sa_relationship_kwargs)
                rel_value = relationship(relationship_to, *rel_args, **rel_kwargs)
                setattr(cls, rel_name, rel_value)  # Fix #315
            # SQLAlchemy no longer uses dict_
            # Ref: https://github.com/sqlalchemy/sqlalchemy/commit/428ea01f00a9cc7f85e435018565eb6da7af1b77
            # Tag: 1.4.36
            DeclarativeMeta.__init__(cls, classname, bases, dict_, **kw)
        else:
            ModelMetaclass.__init__(cls, classname, bases, dict_, **kw)


def is_optional_type(type_: Any) -> bool:
    return get_origin(type_) is Union and type(None) in get_args(type_)


def is_annotated_type(type_: Any) -> bool:
    return get_origin(type_) is Annotated


def base_type_to_sa_type(type_: Any, metadata: MetaData) -> Any:
    if issubclass(type_, Enum):
        return sa_Enum(type_)
    if issubclass(
        type_,
        (
            str,
            ipaddress.IPv4Address,
            ipaddress.IPv4Network,
            ipaddress.IPv6Address,
            ipaddress.IPv6Network,
            Path,
            EmailStr,
        ),
    ):
        max_length = getattr(metadata, "max_length", None)
        if max_length:
            return AutoString(length=max_length)
        return AutoString
    if issubclass(type_, float):
        return Float
    if issubclass(type_, bool):
        return Boolean
    if issubclass(type_, int):
        return Integer
    if issubclass(type_, datetime):
        return DateTime
    if issubclass(type_, date):
        return Date
    if issubclass(type_, timedelta):
        return Interval
    if issubclass(type_, time):
        return Time
    if issubclass(type_, bytes):
        return LargeBinary
    if issubclass(type_, Decimal):
        return Numeric(
            precision=getattr(metadata, "max_digits", None),
            scale=getattr(metadata, "decimal_places", None),
        )
    if issubclass(type_, uuid.UUID):
        return Uuid
    if issubclass(
        type_,
        (
            dict,
            BaseModel,
        ),
    ):
        return JSON
    raise ValueError(f"{type_} has no matching SQLAlchemy type")


def get_sqlalchemy_type(field: Any) -> Any:
    if IS_PYDANTIC_V2:
        field_info = field
    else:
        field_info = field.field_info
    sa_type = getattr(field_info, "sa_type", Undefined)  # noqa: B009
    if sa_type is not Undefined:
        return sa_type

    type_ = get_sa_type_from_field(field)
    metadata = get_field_metadata(field)

    # Check enums first as an enum can also be a str, needed by Pydantic/FastAPI
    if is_annotated_type(type_):
        type_ = get_args(type_)[0]

    origin_type = get_origin(type_)
    if issubclass(type_, list) or origin_type is list:
        type_args = get_args(type_)
        if not type_args:
            type_args = get_args(field.annotation)
        if not type_args:
            raise ValueError(f"List type {type_} has no inner type")

        type_ = type_args[0]
        sa_type_ = base_type_to_sa_type(type_, metadata)

        if issubclass(sa_type_, JSON):
            return sa_type_

        return ARRAY(sa_type_)

    return base_type_to_sa_type(type_, metadata)


def get_column_from_field(field: Any) -> Union[Column, MappedSQLExpression[Any]]:  # type: ignore
    if IS_PYDANTIC_V2:
        field_info = field
    else:
        field_info = field.field_info
    sa_column = getattr(field_info, "sa_column", Undefined)
    if isinstance(sa_column, (Column, MappedSQLExpression)):
        return sa_column
    sa_type = get_sqlalchemy_type(field)
    primary_key = getattr(field_info, "primary_key", Undefined)
    if primary_key is Undefined:
        primary_key = False
    index = getattr(field_info, "index", Undefined)
    if index is Undefined:
        index = False
    nullable = not primary_key and is_field_noneable(field)
    # Override derived nullability if the nullable property is set explicitly
    # on the field
    field_nullable = getattr(field_info, "nullable", Undefined)  # noqa: B009
    if field_nullable is not Undefined:
        assert not isinstance(field_nullable, UndefinedType)
        nullable = field_nullable
    args = []
    foreign_key = getattr(field_info, "foreign_key", Undefined)
    if foreign_key is Undefined:
        foreign_key = None
    unique = getattr(field_info, "unique", Undefined)
    if unique is Undefined:
        unique = False
    if foreign_key:
        if field_info.ondelete == "SET NULL" and not nullable:
            raise RuntimeError('ondelete="SET NULL" requires nullable=True')
        assert isinstance(foreign_key, str)
        ondelete = getattr(field_info, "ondelete", Undefined)
        if ondelete is Undefined:
            ondelete = None
        assert isinstance(ondelete, (str, type(None)))  # for typing
        args.append(ForeignKey(foreign_key, ondelete=ondelete))
    kwargs = {
        "primary_key": primary_key,
        "nullable": nullable,
        "index": index,
        "unique": unique,
    }
    sa_default = Undefined
    if field_info.default_factory:
        sa_default = field_info.default_factory
    elif field_info.default is not Undefined:
        sa_default = field_info.default
    if sa_default is not Undefined:
        kwargs["default"] = sa_default
    sa_column_args = getattr(field_info, "sa_column_args", Undefined)
    if sa_column_args is not Undefined:
        args.extend(list(cast(Sequence[Any], sa_column_args)))
    sa_column_kwargs = getattr(field_info, "sa_column_kwargs", Undefined)
    if sa_column_kwargs is not Undefined:
        kwargs.update(cast(Dict[Any, Any], sa_column_kwargs))
    return Column(sa_type, *args, **kwargs)  # type: ignore


class_registry = weakref.WeakValueDictionary()  # type: ignore

default_registry = registry()

_TSQLModel = TypeVar("_TSQLModel", bound="SQLModel")


class SQLModel(BaseModel, metaclass=SQLModelMetaclass, registry=default_registry):
    # SQLAlchemy needs to set weakref(s), Pydantic will set the other slots values
    __slots__ = ("__weakref__",)
    __tablename__: ClassVar[Union[str, Callable[..., str]]]
    __sqlmodel_relationships__: ClassVar[Dict[str, RelationshipProperty[Any]]]
    __sqlalchemy_association_proxies__: ClassVar[Dict[str, AssociationProxy]]
    __name__: ClassVar[str]
    metadata: ClassVar[MetaData]
    __allow_unmapped__ = True  # https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-20-step-six

    if IS_PYDANTIC_V2:
        model_config = SQLModelConfig(from_attributes=True, use_enum_values=True)
    else:

        class Config:
            orm_mode = True

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        new_object = super().__new__(cls)
        # SQLAlchemy doesn't call __init__ on the base class when querying from DB
        # Ref: https://docs.sqlalchemy.org/en/14/orm/constructors.html
        # Set __fields_set__ here, that would have been set when calling __init__
        # in the Pydantic model so that when SQLAlchemy sets attributes that are
        # added (e.g. when querying from DB) to the __fields_set__, this already exists
        init_pydantic_private_attrs(new_object)
        return new_object

    def __init__(__pydantic_self__, **data: Any) -> None:
        # Uses something other than `self` the first arg to allow "self" as a
        # settable attribute

        # SQLAlchemy does very dark black magic and modifies the __init__ method in
        # sqlalchemy.orm.instrumentation._generate_init()
        # so, to make SQLAlchemy work, it's needed to explicitly call __init__ to
        # trigger all the SQLAlchemy logic, it doesn't work using cls.__new__, setting
        # attributes obj.__dict__, etc. The __init__ method has to be called. But
        # there are cases where calling all the default logic is not ideal, e.g.
        # when calling Model.model_validate(), as the validation is done outside
        # of instance creation.
        # At the same time, __init__ is what users would normally call, by creating
        # a new instance, which should have validation and all the default logic.
        # So, to be able to set up the internal SQLAlchemy logic alone without
        # executing the rest, and support things like Model.model_validate(), we
        # use a contextvar to know if we should execute everything.
        if finish_init.get():
            sqlmodel_init(self=__pydantic_self__, data=data)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_sa_instance_state"}:
            self.__dict__[name] = value
            return
        else:
            # Convert Pydantic objects to table models for relationships
            if (
                is_table_model_class(self.__class__)
                and name in self.__sqlmodel_relationships__
                and value is not None
            ):
                value = _convert_pydantic_to_table_model(
                    value, name, self.__class__, self
                )

            # Set in SQLAlchemy, before Pydantic to trigger events and updates
            if is_table_model_class(self.__class__) and is_instrumented(self, name):  # type: ignore[no-untyped-call]
                set_attribute(self, name, value)
            # Set in SQLAlchemy association proxies
            if (
                is_table_model_class(self.__class__)
                and name in self.__sqlalchemy_association_proxies__
            ):
                association_proxy = self.__sqlalchemy_association_proxies__[name]
                association_proxy.__set__(self, value)
            # Set in Pydantic model to trigger possible validation changes, only for
            # non relationship values
            if (
                name not in self.__sqlmodel_relationships__
                and name not in self.__sqlalchemy_association_proxies__
            ):
                super().__setattr__(name, value)

    def __repr_args__(self) -> Sequence[Tuple[Optional[str], Any]]:
        # Don't show SQLAlchemy private attributes
        return [
            (k, v)
            for k, v in super().__repr_args__()
            if not (isinstance(k, str) and k.startswith("_sa_"))
        ]

    @declared_attr  # type: ignore
    def __tablename__(cls) -> str:
        return cls.__name__.lower()

    @classmethod
    def model_validate(
        cls: Type[_TSQLModel],
        obj: Any,
        *,
        strict: Union[bool, None] = None,
        from_attributes: Union[bool, None] = None,
        context: Union[Dict[str, Any], None] = None,
        update: Union[Dict[str, Any], None] = None,
    ) -> _TSQLModel:
        return sqlmodel_validate(
            cls=cls,
            obj=obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            update=update,
        )

    def model_dump(
        self,
        *,
        mode: Union[Literal["json", "python"], str] = "python",
        include: Union[IncEx, None] = None,
        exclude: Union[IncEx, None] = None,
        context: Union[Dict[str, Any], None] = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: bool = True,
        serialize_as_any: bool = False,
    ) -> Dict[str, Any]:
        if PYDANTIC_VERSION >= "2.7.0":
            extra_kwargs: Dict[str, Any] = {
                "context": context,
                "serialize_as_any": serialize_as_any,
            }
        else:
            extra_kwargs = {}
        if IS_PYDANTIC_V2:
            return super().model_dump(
                mode=mode,
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
                round_trip=round_trip,
                warnings=warnings,
                **extra_kwargs,
            )
        else:
            return super().dict(
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=exclude_none,
            )

    @deprecated(
        """
        🚨 `obj.dict()` was deprecated in SQLModel 0.0.14, you should
        instead use `obj.model_dump()`.
        """
    )
    def dict(
        self,
        *,
        include: Union[IncEx, None] = None,
        exclude: Union[IncEx, None] = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> Dict[str, Any]:
        return self.model_dump(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    @classmethod
    @deprecated(
        """
        🚨 `obj.from_orm(data)` was deprecated in SQLModel 0.0.14, you should
        instead use `obj.model_validate(data)`.
        """
    )
    def from_orm(
        cls: Type[_TSQLModel], obj: Any, update: Optional[Dict[str, Any]] = None
    ) -> _TSQLModel:
        return cls.model_validate(obj, update=update)

    @classmethod
    @deprecated(
        """
        🚨 `obj.parse_obj(data)` was deprecated in SQLModel 0.0.14, you should
        instead use `obj.model_validate(data)`.
        """
    )
    def parse_obj(
        cls: Type[_TSQLModel], obj: Any, update: Optional[Dict[str, Any]] = None
    ) -> _TSQLModel:
        if not IS_PYDANTIC_V2:
            obj = cls._enforce_dict_if_root(obj)  # type: ignore[attr-defined] # noqa
        return cls.model_validate(obj, update=update)

    # From Pydantic, override to only show keys from fields, omit SQLAlchemy attributes
    @deprecated(
        """
        🚨 You should not access `obj._calculate_keys()` directly.

        It is only useful for Pydantic v1.X, you should probably upgrade to
        Pydantic v2.X.
        """,
        category=None,
    )
    def _calculate_keys(
        self,
        include: Optional[Mapping[Union[int, str], Any]],
        exclude: Optional[Mapping[Union[int, str], Any]],
        exclude_unset: bool,
        update: Optional[Dict[str, Any]] = None,
    ) -> Optional[AbstractSet[str]]:
        return _calculate_keys(
            self,
            include=include,
            exclude=exclude,
            exclude_unset=exclude_unset,
            update=update,
        )

    def sqlmodel_update(
        self: _TSQLModel,
        obj: Union[Dict[str, Any], BaseModel],
        *,
        update: Union[Dict[str, Any], None] = None,
    ) -> _TSQLModel:
        use_update = (update or {}).copy()
        if isinstance(obj, dict):
            for key, value in {**obj, **use_update}.items():
                if key in get_model_fields(self):
                    setattr(self, key, value)
        elif isinstance(obj, BaseModel):
            for key in get_model_fields(obj):
                if key in use_update:
                    value = use_update.pop(key)
                else:
                    value = getattr(obj, key)
                setattr(self, key, value)
            for remaining_key in use_update:
                if remaining_key in get_model_fields(self):
                    value = use_update.pop(remaining_key)
                    setattr(self, remaining_key, value)
        else:
            raise ValueError(
                "Can't use sqlmodel_update() with something that "
                f"is not a dict or SQLModel or Pydantic model: {obj}"
            )
        return self


def _convert_pydantic_to_table_model(
    value: Any,
    relationship_name: str,
    owner_class: Type["SQLModel"],
    instance: Optional["SQLModel"] = None,
) -> Any:
    """
    Convert Pydantic objects to table models for relationship assignments.

    Args:
        value: The value being assigned to the relationship
        relationship_name: Name of the relationship attribute
        owner_class: The class that owns the relationship
        instance: The SQLModel instance (for session context)

    Returns:
        Converted value(s) - table model instances instead of Pydantic objects
    """
    from typing import get_args, get_origin

    # Get the relationship annotation to determine target type
    if relationship_name not in owner_class.__annotations__:
        return value

    raw_ann = owner_class.__annotations__[relationship_name]
    origin = get_origin(raw_ann)

    # Handle Mapped[...] annotations
    if origin is Mapped:
        ann = raw_ann.__args__[0]
    else:
        ann = raw_ann

    # Get the target relationship type
    try:
        rel_info = owner_class.__sqlmodel_relationships__[relationship_name]
        relationship_to = get_relationship_to(
            name=relationship_name, rel_info=rel_info, annotation=ann
        )
    except (KeyError, AttributeError):
        return value

    # Handle list/sequence relationships
    list_origin = get_origin(ann)
    if list_origin is list:
        target_type = get_args(ann)[0]
        if isinstance(target_type, str):
            # Forward reference - try to resolve from SQLAlchemy's registry
            try:
                resolved_type = default_registry._class_registry.get(target_type)
                if resolved_type is not None:
                    target_type = resolved_type
                else:
                    target_type = relationship_to
            except Exception:
                target_type = relationship_to
        else:
            target_type = relationship_to

        if isinstance(value, (list, tuple)):
            converted_items = []
            for item in value:
                converted_item = _convert_single_pydantic_to_table_model(
                    item, target_type, instance
                )
                converted_items.append(converted_item)
            return converted_items
    else:
        # Single relationship
        target_type = relationship_to
        if isinstance(target_type, str):
            # Forward reference - try to resolve from SQLAlchemy's registry
            try:
                resolved_type = default_registry._class_registry.get(target_type)
                if resolved_type is not None:
                    target_type = resolved_type
            except Exception:
                pass

        return _convert_single_pydantic_to_table_model(value, target_type, instance)

    return value


def _convert_single_pydantic_to_table_model(
    item: Any, target_type: Any, instance: Optional["SQLModel"] = None
) -> Any:
    """
    Convert a single Pydantic object to a table model.

    Args:
        item: The Pydantic object to convert
        target_type: The target table model type
        instance: The SQLModel instance (for session context)

    Returns:
        Converted table model instance or original item if no conversion needed
    """
    # If item is None, return as-is
    if item is None:
        return item

    resolved_target_type = target_type
    if isinstance(target_type, str):
        try:
            # Attempt to resolve forward reference from the default registry
            # This was part of the original logic and should be kept
            resolved_type_from_registry = default_registry._class_registry.get(
                target_type
            )
            if resolved_type_from_registry is not None:
                resolved_target_type = resolved_type_from_registry
        except Exception:
            # If resolution fails, and it's still a string, we might not be able to convert
            # However, the original issue implies 'relationship_to' in the caller
            # `_convert_pydantic_to_table_model` should provide a resolved type.
            # For safety, if it's still a string here, and item is a simple Pydantic model,
            # it's best to return item to avoid errors if no concrete type is found.
            if (
                isinstance(resolved_target_type, str)
                and isinstance(item, BaseModel)
                and hasattr(item, "__class__")
                and not is_table_model_class(item.__class__)
            ):
                return item  # Fallback if no concrete type can be determined
            pass  # Continue if resolved_target_type is now a class or item is not a simple Pydantic model

    # If resolved_target_type is still a string and not a class, we cannot proceed with conversion.
    # This can happen if the forward reference cannot be resolved.
    if isinstance(resolved_target_type, str):
        return item

    # If item is already the correct type, return as-is
    if isinstance(item, resolved_target_type):
        return item

    # Check if resolved_target_type is a SQLModel table class
    # This check should be on resolved_target_type, not target_type
    if not (
        hasattr(resolved_target_type, "__mro__")
        and any(
            hasattr(cls, "__sqlmodel_relationships__")
            for cls in resolved_target_type.__mro__
        )
    ):
        return item

    # Check if target is a table model using resolved_target_type
    if not is_table_model_class(resolved_target_type):
        return item

    # Check if item is a BaseModel (Pydantic model) but not a table model
    if (
        isinstance(item, BaseModel)
        and hasattr(item, "__class__")
        and not is_table_model_class(item.__class__)
    ):
        # Convert Pydantic model to table model
        try:
            # Get the data from the Pydantic model
            if hasattr(item, "model_dump"):
                # Pydantic v2
                data = item.model_dump()
            else:
                # Pydantic v1
                data = item.dict()

            # If instance is available and item has an ID, try to find existing record
            if instance is not None and "id" in data and data["id"] is not None:
                from sqlalchemy.orm import object_session

                session = object_session(instance)
                if session is not None:
                    # Try to find existing record by ID
                    existing_record = session.get(resolved_target_type, data["id"])
                    if existing_record is not None:
                        # Update existing record with new data
                        for key, value in data.items():
                            if key != "id" and hasattr(existing_record, key):
                                setattr(existing_record, key, value)
                        return existing_record

            # Create new table model instance using resolved_target_type
            return resolved_target_type(**data)
        except Exception:
            # If conversion fails, return original item
            return item

    # Check if item is a dictionary that should be converted to table model
    elif isinstance(item, dict):
        try:
            # If instance is available and item has an ID, try to find existing record
            if instance is not None and "id" in item and item["id"] is not None:
                from sqlalchemy.orm import object_session

                session = object_session(instance)
                if session is not None:
                    # Try to find existing record by ID
                    existing_record = session.get(resolved_target_type, item["id"])
                    if existing_record is not None:
                        # Update existing record with new data
                        for key, value in item.items():
                            if key != "id" and hasattr(existing_record, key):
                                setattr(existing_record, key, value)
                        return existing_record

            # Create new table model instance from dictionary
            return resolved_target_type(**item)
        except Exception:
            # If conversion fails, return original item
            return item

    return item
