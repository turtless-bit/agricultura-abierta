"""Uso:  pip install tflite && python scripts/fijar_lote_tflite.py models/papa_*.tflite

Fija el tamaño de lote de un .tflite en 1: cambia los -1 de shape_signature por 1.
Es el mismo modelo (mismos pesos); solo deja de declarar que acepta lotes de tamaño variable,
porque LiteRT.js en el navegador exige formas fijas."""
import struct, sys
import tflite

def fijar(entrada, salida):
    buf = bytearray(open(entrada, "rb").read())
    m = tflite.Model.GetRootAsModel(buf, 0)
    cambios = 0
    for s in range(m.SubgraphsLength()):
        sg = m.Subgraphs(s)
        for t in range(sg.TensorsLength()):
            ten = sg.Tensors(t)
            o = ten._tab.Offset(18)  # campo shape_signature
            if not o:
                continue
            inicio = ten._tab.Vector(o)
            for j in range(ten.ShapeSignatureLength()):
                pos = inicio + 4 * j
                if struct.unpack_from("<i", buf, pos)[0] == -1:
                    struct.pack_into("<i", buf, pos, 1); cambios += 1
    open(salida, "wb").write(buf)
    m2 = tflite.Model.GetRootAsModel(buf, 0); sg = m2.Subgraphs(0)
    ent = sg.Tensors(sg.Inputs(0))
    print(f"{salida}: {cambios} dimensiones fijadas; entrada shape={ent.ShapeAsNumpy().tolist()} signature={ent.ShapeSignatureAsNumpy().tolist()}")

for a in sys.argv[1:]:
    fijar(a, a)
