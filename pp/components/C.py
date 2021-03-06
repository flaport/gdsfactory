from typing import Tuple, Union

from pp.cell import cell
from pp.component import Component
from pp.layers import LAYER


@cell
def C(
    width: Union[int, float] = 1,
    size: Tuple[int, int] = (10, 20),
    layer: Tuple[int, int] = LAYER.M3,
) -> Component:
    """ Generates a 'C' geometry with ports on both ends. Based on phidl

    Args:
        width: of the line
        size: length and height of the base
        layer:

    .. plot::
      :include-source:

      import pp

      c = pp.c.C(width=1, size=(10, 20), layer=pp.LAYER.M3)
      pp.plotgds(c)
    """
    D = Component()
    w = width / 2
    s1, s2 = size
    points = [
        (-w, -w),
        (s1, -w),
        (s1, w),
        (w, w),
        (w, s2 - w),
        (s1, s2 - w),
        (s1, s2 + w),
        (-w, s2 + w),
        (-w, -w),
    ]
    D.add_polygon(points, layer=layer)
    D.add_port(name=1, midpoint=(s1, s2), width=width, orientation=0)
    D.add_port(name=2, midpoint=(s1, 0), width=width, orientation=0)
    return D


if __name__ == "__main__":
    import pp

    c = C()
    pp.show(c)
