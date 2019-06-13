"""Basic functions for dataset loaders"""

import random
import tensorflow as tf


class _datalist(list):
    """The same thing as list, but don't count in nested structure
    """
    pass

def sparse_batch(batch_size, drop_remainder=False, num_parallel_calls=8):
    def sparsify(tensors):
        atom_ind = tf.cast(tf.where(tensors['elems']), tf.int32)
        ind_1 = atom_ind[:,:1]
        ind_sp = tf.cumsum(tf.ones(tf.shape(ind_1), tf.int32))-1
        tensors['ind_1'] = ind_1
        elems = tf.gather_nd(tensors['elems'], atom_ind)
        coord = tf.gather_nd(tensors['coord'], atom_ind)
        tensors['elems'] = elems
        tensors['coord'] = coord
        if 'f_data' in tensors:
            tensors['f_data'] = tf.gather_nd(tensors['f_data'], atom_ind)
        return tensors
    return lambda dataset: \
        dataset.padded_batch(batch_size, dataset.output_shapes,
                             drop_remainder=drop_remainder).map(
                                 sparsify, num_parallel_calls)

def map_nested(fn, nested):
    """Map fn to the nested structure
    """
    if isinstance(nested, dict):
        return {k: map_nested(fn, v) for k,v in nested.items()}
    if isinstance(nested, list) and type(nested) != _datalist:
        return [map_nested(fn, v) for v in nested]
    else:
        return fn(nested)

def flatten_nested(nested):
    """Retun a list of the nested elements
    """
    if isinstance(nested, dict):
        return sum([flatten_nested(v) for v in nested.values()],[])
    if isinstance(nested, list) and type(nested) != _datalist:
        return sum([flatten_nested(v) for v in nested], [])
    else:
        return [nested]

def split_list(data_list, split={'train': 8, 'vali':1, 'test':1},
               shuffle=True, seed=None):
    """
    Split the list according to a given ratio

    Args:
        to_split (list): a list to split
        split_ratio: a nested (list and dict) of split ratio

    Returns:
        A nest structure of splitted data list
    """
    import math
    dummy = _datalist(data_list)
    if shuffle:
        random.seed(seed)
        random.shuffle(dummy)
    data_tot = len(dummy)
    split_tot = float(sum(flatten_nested(split)))
    get_split_num = lambda x: math.ceil(data_tot*x/split_tot)
    split_num = map_nested(get_split_num, split)
    def _pop_data(n):
        to_pop = dummy[:n]
        del dummy[:n]
        return _datalist(to_pop)
    splitted = map_nested(_pop_data, split_num)
    return splitted

def list_loader(pbc=False, force=False, format_dict=None):
    """Decorator for building dataset loaders"""
    from functools import wraps
    if format_dict is None:
        format_dict = {
            'elems': {'dtype':  tf.int32,   'shape': [None]},
            'coord': {'dtype':  tf.float32, 'shape': [None, 3]},
            'e_data': {'dtype': tf.float32, 'shape': []},
        }
        if pbc:
            format_dict['cell'] = {'dtype':  tf.float32, 'shape': [3,3]}
        if force:
            format_dict['f_data'] = {'dtype':  tf.float32, 'shape': [None,3]}
    def decorator(func):
        @wraps(func)
        def data_loader(data_list, split={'train': 8, 'vali':1, 'test':1},
                        shuffle=True, seed=0):
            def _data_generator(data_list):
                for data in data_list:
                    yield func(data)
            dtypes = {k: v['dtype'] for k,v in format_dict.items()}
            shapes = {k: v['shape'] for k,v in format_dict.items()}
            generator_fn = lambda data_list: tf.data.Dataset.from_generator(
                lambda: _data_generator(data_list), dtypes, shapes)
            subsets = split_list(data_list, split, shuffle, seed)
            splitted = map_nested(generator_fn, subsets)
            return splitted
        return data_loader
    return decorator