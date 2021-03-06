import pytest

from pp.components import (
    _components,
    _components_test_ports,
    _containers,
    component_factory,
    waveguide,
)


@pytest.mark.parametrize("component_type", _components_test_ports)
def test_components_ports(component_type, num_regression):
    # pp.clear_cache()
    c = component_factory[component_type]()
    if c.ports:
        num_regression.check(c.get_ports_array())


@pytest.mark.parametrize("component_type", _components)
def test_properties_components(component_type, data_regression):
    # pp.clear_cache()
    c = component_factory[component_type]()
    data_regression.check(c.get_settings())


@pytest.mark.parametrize("component_type", _containers)
def test_properties_containers(component_type, data_regression):
    # pp.clear_cache()
    c = component_factory[component_type](component=waveguide())
    data_regression.check(c.get_settings())
