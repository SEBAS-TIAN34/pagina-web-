import os
import json
import re
import secrets
from decimal import Decimal
from flask import Flask, render_template, jsonify, request
import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

app = Flask(__name__)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
TABLES = {
    "clientes": os.getenv("TABLE_CLIENTES", "clientes"),
    "productos": os.getenv("TABLE_PRODUCTOS", "productos"),
    "ventas": os.getenv("TABLE_VENTAS", "ventas"),
    "compras": os.getenv("TABLE_COMPRAS", "compras"),
    "inventario": os.getenv("TABLE_INVENTARIO", "inventario"),
    "proveedores": os.getenv("TABLE_PROVEEDORES", "proveedores"),
}

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
DYNAMODB_KEYS = {
    "clientes": "clienteId",
    "productos": "productoId",
    "ventas": "ventaId",
}
DYNAMODB_DESERIALIZER = TypeDeserializer()

def dynamodb_error_response(operation, error):
    details = error.response.get("Error", {})
    app.logger.error(
        "DynamoDB %s failed (%s): %s",
        operation,
        details.get("Code", "Unknown"),
        details.get("Message", str(error)),
    )
    return jsonify({
        "error": "No se pudieron cargar los datos. Verifica los permisos de AWS e inténtalo de nuevo."
    }), 500

def scan_table(table_key):
    """Lee los elementos de una tabla DynamoDB, incluyendo paginación."""
    table = dynamodb.Table(TABLES[table_key])
    items = []
    response = table.scan()
    items.extend(response.get("Items", []))
    while response.get("LastEvaluatedKey"):
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    return items

def as_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value

def matching_clients():
    """Return client records matching every supplied, case-insensitive substring filter."""
    filters = {
        key: request.args.get(key, "").strip().casefold()
        for key in ("clienteId", "nombre", "ciudad", "correo")
    }
    clients = scan_table("clientes")
    if not any(filters.values()):
        return clients
    return [
        client for client in clients
        if all(
            not value or value in str(client.get(field, "")).casefold()
            for field, value in filters.items()
        )
    ]

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "region": AWS_REGION, "tables": TABLES})

@app.route("/api/ventas-por-ciudad")
def ventas_por_ciudad():
    try:
        clients = matching_clients()
        clientes = {c.get("clienteId"): c for c in clients}
        productos = {p.get("productoId"): p for p in scan_table("productos")}
        ventas = [v for v in scan_table("ventas") if v.get("clienteId") in clientes]
        grouped = {}
        for venta in ventas:
            cliente = clientes.get(venta.get("clienteId"), {})
            producto = productos.get(venta.get("productoId"), {})
            ciudad = cliente.get("ciudad") or "Sin ciudad"
            importe = as_number(producto.get("precio")) * as_number(venta.get("cantidad"))
            row = grouped.setdefault(ciudad, {"ciudad": ciudad, "cantidadVentas": 0, "unidades": 0, "ingresos": 0})
            row["cantidadVentas"] += 1
            row["unidades"] += int(as_number(venta.get("cantidad")))
            row["ingresos"] += importe
        results = sorted(grouped.values(), key=lambda x: x["ciudad"])
        return jsonify({"results": results, "totalVentas": len(ventas), "matchedClients": len(clients)})
    except ClientError as e:
        return dynamodb_error_response("consulta de ventas por ciudad", e)

@app.route("/api/ingresos-por-categoria")
def ingresos_por_categoria():
    try:
        clientes = {c.get("clienteId") for c in matching_clients()}
        productos = {p.get("productoId"): p for p in scan_table("productos")}
        ventas = [v for v in scan_table("ventas") if v.get("clienteId") in clientes]
        grouped = {}
        for venta in ventas:
            producto = productos.get(venta.get("productoId"), {})
            categoria = producto.get("categoria") or "Sin categoría"
            ingreso = as_number(producto.get("precio")) * as_number(venta.get("cantidad"))
            row = grouped.setdefault(categoria, {"categoria": categoria, "unidades": 0, "ingresos": 0})
            row["unidades"] += int(as_number(venta.get("cantidad")))
            row["ingresos"] += ingreso
        results = sorted(grouped.values(), key=lambda x: x["categoria"])
        return jsonify({
            "results": results,
            "totalIngresos": sum(x["ingresos"] for x in results),
            "matchedClients": len(clientes),
        })
    except ClientError as e:
        return dynamodb_error_response("consulta de ingresos por categoría", e)

@app.route("/api/clientes-por-categoria")
def clientes_por_categoria():
    try:
        client_records = matching_clients()
        clientes = {c.get("clienteId"): c for c in client_records}
        productos = {p.get("productoId"): p for p in scan_table("productos")}
        ventas = scan_table("ventas")
        grouped = {}
        seen = set()
        for venta in ventas:
            cliente = clientes.get(venta.get("clienteId"), {})
            producto = productos.get(venta.get("productoId"), {})
            if not cliente or not producto:
                continue
            categoria = producto.get("categoria") or "Sin categoría"
            key = (cliente.get("clienteId"), categoria)
            if key in seen:
                continue
            seen.add(key)
            grouped.setdefault(categoria, []).append({
                "clienteId": cliente.get("clienteId", ""),
                "nombre": cliente.get("nombre", ""),
                "ciudad": cliente.get("ciudad", ""),
                "correo": cliente.get("correo", ""),
                "categoria": categoria,
            })
        results = [{"categoria": k, "clientes": sorted(v, key=lambda x: x["nombre"])} for k, v in sorted(grouped.items())]
        return jsonify({"results": results, "matchedClients": len(clientes)})
    except ClientError as e:
        return dynamodb_error_response("consulta de clientes por categoría", e)

@app.route("/api/clientes/<cliente_id>")
def buscar_cliente(cliente_id):
    try:
        table = dynamodb.Table(TABLES["clientes"])
        response = table.get_item(Key={"clienteId": cliente_id})
        item = response.get("Item")
        if not item:
            return jsonify({"error": f"No se encontró el cliente {cliente_id}"}), 404
        return jsonify({"cliente": json_safe(item)})
    except ClientError as e:
        return dynamodb_error_response("búsqueda de cliente", e)

@app.route("/api/clientes", methods=["POST"])
def crear_cliente():
    data = request.get_json(silent=True) or {}
    requested_id = (data.get("clienteId") or "").strip().upper()
    nombre = (data.get("nombre") or "").strip()
    ciudad = (data.get("ciudad") or "").strip()
    correo = (data.get("correo") or "").strip()
    if not nombre or not ciudad or not correo:
        return jsonify({"error": "Completa nombre, ciudad y correo."}), 400
    if requested_id and not re.fullmatch(r"C\d{1,12}", requested_id):
        return jsonify({"error": "El ID debe empezar con C y continuar con números (por ejemplo, C000123)."}), 400

    table = dynamodb.Table(TABLES["clientes"])
    for attempt in range(1 if requested_id else 5):
        cliente_id = requested_id or f"C{secrets.randbelow(1_000_000):06d}"
        item = {"clienteId": cliente_id, "nombre": nombre, "ciudad": ciudad, "correo": correo}
        try:
            table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(clienteId)"
            )
            return jsonify({"message": "Cliente guardado correctamente.", "cliente": item}), 201
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "ConditionalCheckFailedException":
                if requested_id:
                    return jsonify({"error": f"Ya existe un cliente con ID {cliente_id}."}), 409
                continue
            return dynamodb_error_response("registro de cliente", e)
    return jsonify({"error": "No se pudo generar un ID de cliente único. Inténtalo de nuevo."}), 503

@app.route("/api/subir-archivo", methods=["POST"])
def subir_archivo():
    """Importa archivos JSON exportados como solicitudes PutRequest de DynamoDB."""
    uploaded_files = request.files.getlist("archivos")
    if not uploaded_files:
        uploaded_files = request.files.getlist("archivo")
    uploaded_files = [file for file in uploaded_files if file and file.filename]
    if not uploaded_files:
        return jsonify({"error": "Selecciona al menos un archivo JSON."}), 400

    prepared_files = []
    for uploaded in uploaded_files:
        if not uploaded.filename.lower().endswith(".json"):
            return jsonify({"error": f"{uploaded.filename}: solo se aceptan archivos .json."}), 400
        try:
            content = json.load(uploaded.stream)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return jsonify({"error": f"{uploaded.filename}: el archivo no contiene JSON válido."}), 400

        if not isinstance(content, dict) or len(content) != 1:
            return jsonify({"error": f"{uploaded.filename}: se esperaba un objeto con una sola tabla."}), 400
        table_key, records = next(iter(content.items()))
        if table_key not in DYNAMODB_KEYS or not isinstance(records, list):
            return jsonify({"error": f"{uploaded.filename}: la tabla debe ser clientes, productos o ventas."}), 400

        items = []
        required_key = DYNAMODB_KEYS[table_key]
        for index, record in enumerate(records, start=1):
            put_request = record.get("PutRequest") if isinstance(record, dict) else None
            attribute_map = put_request.get("Item") if isinstance(put_request, dict) else None
            if not isinstance(attribute_map, dict):
                return jsonify({"error": f"{uploaded.filename}: registro {index} no tiene un PutRequest.Item válido."}), 400
            try:
                item = {
                    name: DYNAMODB_DESERIALIZER.deserialize(value)
                    for name, value in attribute_map.items()
                }
            except (TypeError, ValueError, KeyError) as error:
                return jsonify({"error": f"{uploaded.filename}: atributo inválido en el registro {index}: {error}"}), 400
            if not isinstance(item.get(required_key), str) or not item[required_key]:
                return jsonify({"error": f"{uploaded.filename}: el registro {index} requiere la clave {required_key}."}), 400
            items.append(item)
        prepared_files.append({"filename": uploaded.filename, "table_key": table_key, "items": items})

    inserted = 0
    skipped = 0
    imported_files = []
    try:
        for prepared in prepared_files:
            table = dynamodb.Table(TABLES[prepared["table_key"]])
            file_inserted = 0
            file_skipped = 0
            key_name = DYNAMODB_KEYS[prepared["table_key"]]
            for item in prepared["items"]:
                try:
                    table.put_item(
                        Item=item,
                        ConditionExpression="attribute_not_exists(#pk)",
                        ExpressionAttributeNames={"#pk": key_name},
                    )
                    inserted += 1
                    file_inserted += 1
                except ClientError as error:
                    if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                        raise
                    skipped += 1
                    file_skipped += 1
            imported_files.append({
                "filename": prepared["filename"],
                "table": prepared["table_key"],
                "inserted": file_inserted,
                "skipped": file_skipped,
            })
    except ClientError as error:
        response, status = dynamodb_error_response("importación de archivo", error)
        payload = response.get_json()
        payload.update({
            "error": (
                f"{payload['error']} Antes del error se insertaron {inserted} registros "
                f"y se omitieron {skipped} existentes."
            ),
            "inserted": inserted,
            "skipped": skipped,
            "files": imported_files,
        })
        return jsonify(payload), status

    return jsonify({
        "message": "Importación a DynamoDB completada.",
        "inserted": inserted,
        "skipped": skipped,
        "files": imported_files,
    })

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Ruta no encontrada."}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "80")), debug=False)
