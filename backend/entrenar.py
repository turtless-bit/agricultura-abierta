"""Entrena el modelo de enfermedades de la papa (transfer learning con MobileNetV2).

Dataset: PlantVillage (carpetas Potato___Early_blight, Potato___Late_blight, Potato___healthy).
Descárguelo, por ejemplo, de Kaggle: "PlantVillage dataset" y deje la estructura:

    datos/papa/
        Potato___Early_blight/*.jpg
        Potato___Late_blight/*.jpg
        Potato___healthy/*.jpg

Ejecutar:  .venv/bin/python -m backend.entrenar --datos datos/papa --epocas 10
Genera models/papa_modelo.keras y models/clases.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import tensorflow as tf

RAIZ = Path(__file__).resolve().parent.parent
TAM = (224, 224)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(RAIZ / "datos" / "papa"))
    ap.add_argument("--epocas", type=int, default=10)
    ap.add_argument("--lote", type=int, default=32)
    args = ap.parse_args()

    kw = dict(validation_split=0.2, seed=42, image_size=TAM, batch_size=args.lote)
    entren = tf.keras.utils.image_dataset_from_directory(args.datos, subset="training", **kw)
    valid = tf.keras.utils.image_dataset_from_directory(args.datos, subset="validation", **kw)
    clases = entren.class_names
    print("Clases:", clases)

    aumento = tf.keras.Sequential([
        tf.keras.layers.RandomFlip("horizontal_and_vertical"),
        tf.keras.layers.RandomRotation(0.2),
        tf.keras.layers.RandomZoom(0.15),
        tf.keras.layers.RandomContrast(0.2),
    ])
    base = tf.keras.applications.MobileNetV2(input_shape=TAM + (3,), include_top=False, weights="imagenet")
    base.trainable = False

    entradas = tf.keras.Input(shape=TAM + (3,))  # píxeles 0-255
    x = aumento(entradas)
    x = tf.keras.layers.Rescaling(1 / 127.5, offset=-1)(x)  # equivalente a preprocess_input
    x = base(x, training=False)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    salidas = tf.keras.layers.Dense(len(clases), activation="softmax")(x)
    modelo = tf.keras.Model(entradas, salidas)

    autotune = tf.data.AUTOTUNE
    entren, valid = entren.prefetch(autotune), valid.prefetch(autotune)

    modelo.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                   loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    modelo.fit(entren, validation_data=valid, epochs=args.epocas)

    # Ajuste fino de las últimas capas
    base.trainable = True
    for capa in base.layers[:-30]:
        capa.trainable = False
    modelo.compile(optimizer=tf.keras.optimizers.Adam(1e-5),
                   loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    modelo.fit(entren, validation_data=valid, epochs=max(3, args.epocas // 2))

    salida = RAIZ / "models"
    salida.mkdir(exist_ok=True)
    modelo.save(salida / "papa_modelo.keras")
    (salida / "clases.json").write_text(json.dumps(clases))
    print("Modelo guardado en", salida / "papa_modelo.keras")


if __name__ == "__main__":
    main()
