# Copyright (c) OpenMMLab. All rights reserved.
import inspect
from typing import Dict, Tuple, Union

import torch.nn as nn
from mmengine.registry import MODELS
from mmengine.utils import is_tuple_of
from mmengine.utils.dl_utils.parrots_wrapper import (SyncBatchNorm, _BatchNorm,
                                                     _InstanceNorm)

# MODELS.register_module('BN', module=nn.BatchNorm2d)
# MODELS.register_module('BN1d', module=nn.BatchNorm1d)
# MODELS.register_module('BN2d', module=nn.BatchNorm2d)
# MODELS.register_module('BN3d', module=nn.BatchNorm3d)
# MODELS.register_module('SyncBN', module=SyncBatchNorm)
# MODELS.register_module('GN', module=nn.GroupNorm)
# MODELS.register_module('LN', module=nn.LayerNorm)
# MODELS.register_module('IN', module=nn.InstanceNorm2d)
# MODELS.register_module('IN1d', module=nn.InstanceNorm1d)
# MODELS.register_module('IN2d', module=nn.InstanceNorm2d)
# MODELS.register_module('IN3d', module=nn.InstanceNorm3d)


def infer_abbr(class_type):
    """Infer abbreviation from the class name.

    When we build a norm layer with `build_norm_layer()`, we want to preserve
    the norm type in variable names, e.g, self.bn1, self.gn. This method will
    infer the abbreviation to map class types to abbreviations.

    Rule 1: If the class has the property "_abbr_", return the property.
    Rule 2: If the parent class is _BatchNorm, GroupNorm, LayerNorm or
    InstanceNorm, the abbreviation of this layer will be "bn", "gn", "ln" and
    "in" respectively.
    Rule 3: If the class name contains "batch", "group", "layer" or "instance",
    the abbreviation of this layer will be "bn", "gn", "ln" and "in"
    respectively.
    Rule 4: Otherwise, the abbreviation falls back to "norm".

    Args:
        class_type (type): The norm layer type.

    Returns:
        str: The inferred abbreviation.
    """
    if not inspect.isclass(class_type):
        raise TypeError(
            f'class_type must be a type, but got {type(class_type)}')
    if hasattr(class_type, '_abbr_'):
        return class_type._abbr_
    if issubclass(class_type, _InstanceNorm):  # IN is a subclass of BN
        return 'in'
    elif issubclass(class_type, _BatchNorm):
        return 'bn'
    elif issubclass(class_type, nn.GroupNorm):
        return 'gn'
    elif issubclass(class_type, nn.LayerNorm):
        return 'ln'
    else:
        class_name = class_type.__name__.lower()
        if 'batch' in class_name:
            return 'bn'
        elif 'group' in class_name:
            return 'gn'
        elif 'layer' in class_name:
            return 'ln'
        elif 'instance' in class_name:
            return 'in'
        else:
            return 'norm_layer'


def build_norm_layer(cfg: Dict,
                     num_features: int,
                     postfix: Union[int, str] = '') -> Tuple[str, nn.Module]:
    """Build normalization layer.

    Args:
        cfg (dict): The norm layer config, which should contain:

            - type (str): Layer type.
            - layer args: Args needed to instantiate a norm layer.
            - requires_grad (bool, optional): Whether stop gradient updates.
        num_features (int): Number of input channels.
        postfix (int | str): The postfix to be appended into norm abbreviation
            to create named layer.

    Returns:
        tuple[str, nn.Module]: The first element is the layer name consisting
        of abbreviation and postfix, e.g., bn1, gn. The second element is the
        created norm layer.
    """
    norm_layer_map = {
        'BN': nn.BatchNorm2d,
        'BN1d': nn.BatchNorm1d,
        'BN2d': nn.BatchNorm2d,
        'BN3d': nn.BatchNorm3d,
        'SyncBN': SyncBatchNorm,
        'GN': nn.GroupNorm,
        'LN': nn.LayerNorm,
        'IN': nn.InstanceNorm2d,
        'IN1d': nn.InstanceNorm1d,
        'IN2d': nn.InstanceNorm2d,
        'IN3d': nn.InstanceNorm3d,
    }
    
    if not isinstance(cfg, dict):
        raise TypeError('cfg must be a dict')
    if 'type' not in cfg:
        raise KeyError('the cfg dict must contain the key "type"')
    cfg_ = cfg.copy()

    layer_type = cfg_.pop('type')

    # if inspect.isclass(layer_type):
    #     norm_layer = layer_type
    # else:
    #     # Switch registry to the target scope. If `norm_layer` cannot be found
    #     # in the registry, fallback to search `norm_layer` in the
    #     # mmengine.MODELS.
    #     with MODELS.switch_scope_and_registry(None) as registry:
    #         norm_layer = registry.get(layer_type)
    #     if norm_layer is None:
    #         raise KeyError(f'Cannot find {norm_layer} in registry under '
    #                        f'scope name {registry.scope}')
    
    if layer_type in norm_layer_map:
        norm_layer = norm_layer_map[layer_type]
    else:
        raise KeyError(f'Unrecognized norm type {layer_type}')
    
    abbr = infer_abbr(norm_layer)

    assert isinstance(postfix, (int, str))
    name = abbr + str(postfix)

    requires_grad = cfg_.pop('requires_grad', True)
    cfg_.setdefault('eps', 1e-5)
    if norm_layer is not nn.GroupNorm:
        layer = norm_layer(num_features, **cfg_)
        if layer_type == 'SyncBN' and hasattr(layer, '_specify_ddp_gpu_num'):
            layer._specify_ddp_gpu_num(1)
    else:
        assert 'num_groups' in cfg_
        layer = norm_layer(num_channels=num_features, **cfg_)

    for param in layer.parameters():
        param.requires_grad = requires_grad

    return name, layer


def is_norm(layer: nn.Module,
            exclude: Union[type, tuple, None] = None) -> bool:
    """Check if a layer is a normalization layer.

    Args:
        layer (nn.Module): The layer to be checked.
        exclude (type | tuple[type]): Types to be excluded.

    Returns:
        bool: Whether the layer is a norm layer.
    """
    if exclude is not None:
        if not isinstance(exclude, tuple):
            exclude = (exclude, )
        if not is_tuple_of(exclude, type):
            raise TypeError(
                f'"exclude" must be either None or type or a tuple of types, '
                f'but got {type(exclude)}: {exclude}')

    if exclude and isinstance(layer, exclude):
        return False

    all_norm_bases = (_BatchNorm, _InstanceNorm, nn.GroupNorm, nn.LayerNorm)
    return isinstance(layer, all_norm_bases)
