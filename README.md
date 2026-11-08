# DynamoPanel — aplicación de consultas con Flask y DynamoDB

Interfaz sencilla para los retos de consultas de ventas, ingresos por categoría y clientes por categoría, además de buscar y registrar clientes.

La página permite importar los archivos JSON exportados en formato `BatchWriteItem` de DynamoDB. Selecciona uno o varios archivos `clientes.json`, `productos.json` y `ventas.json` en “Importar datos”; los elementos con IDs que ya existan se omiten y no se sobrescriben. Al registrar un cliente, puedes escribir un ID que empiece por `C` seguido de números o dejarlo vacío para generar uno aleatorio con el formato `C483921`. Los IDs escritos que ya existan se rechazan; los generados se vuelven a intentar si hay una colisión.

Los retos 3, 4 y 5 tienen filtros opcionales por ID, nombre, ciudad y correo. Los valores se buscan como coincidencias parciales, sin distinguir mayúsculas, y al completar más de un campo todos deben coincidir. Los resultados y totales se recalculan para las ventas de los clientes encontrados.

## Tablas esperadas
- `clientes`: `clienteId`, `nombre`, `ciudad`, `correo`
- `productos`: `productoId`, `nombre`, `categoria`, `precio`
- `ventas`: `ventaId`, `fecha`, `clienteId`, `productoId`, `cantidad`
- También conserva las tablas `compras`, `inventario` y `proveedores`; esta interfaz no las modifica.

## Ejecutar localmente
Requiere Python 3.9+ y credenciales AWS configuradas con acceso a DynamoDB.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export AWS_REGION=us-east-1
export SECRET_KEY="cambia-esta-clave-en-produccion"
python app.py
```

La aplicación escucha en `127.0.0.1` por defecto. Para publicarla detrás de un proxy o en una instancia EC2, configura explícitamente la interfaz:

```bash
export HOST=0.0.0.0
```

En Amazon Linux EC2, para una prueba rápida (con los paquetes ya instalados o después de `pip install -r requirements.txt`):

```bash
cd dynamo_consultas_web
export HOST=0.0.0.0
export SECRET_KEY="cambia-esta-clave-en-produccion"
sudo python3 -m pip install -r requirements.txt
sudo python3 app.py
```

Luego abre `http://IP-PUBLICA-DE-EC2/`. Si el puerto 80 ya está ocupado, no arranques otro proceso: primero identifica el proceso con `sudo ss -ltnp | grep ':80'`.

## Permisos IAM
El rol asociado a EC2 necesita, como mínimo:
- `dynamodb:Scan` en las tablas `clientes`, `productos` y `ventas`.
- `dynamodb:GetItem` y `dynamodb:PutItem` en la tabla `clientes`.
- `dynamodb:PutItem` en las tablas `productos` y `ventas` para importar sus archivos JSON.

La importación también necesita `dynamodb:PutItem` en cada tabla que se vaya a cargar. No necesita `dynamodb:ListTables` para esta aplicación. Aplica el principio de mínimo privilegio y limita los recursos a las tablas indicadas.

## Importante
- La consulta de ingresos calcula `precio × cantidad` porque los registros de `ventas` no incluyen precio ni total.
- “Ventas por ciudad” usa la ciudad del cliente asociado a cada venta, ya que la tabla `ventas` no contiene un campo `ciudad`.
- La opción “Importar datos” acepta archivos JSON `BatchWriteItem` de las tablas `clientes`, `productos` o `ventas`, los inserta en DynamoDB y omite claves primarias ya existentes.
- Las tablas deben tener datos reales en AWS. Los archivos JSON de ejemplo no se cargan solos.
- Las consultas usan `Scan`, apropiado para una práctica pequeña; para volúmenes grandes se recomienda diseñar índices/consultas más eficientes.
