from flask import Flask, request, redirect, url_for, render_template, session
import pyodbc
import numpy_financial as npf
from datetime import timedelta
import uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your secret key'

def connect_to_database():
    Server = 'CHARLIE\MENTAL'
    database = '23'
    userDB = 'sa'
    password = '12345'

    try:
        conexion = pyodbc.connect('DRIVER={SQL SERVER};SERVER='+Server+';DATABASE='+database+';UID='+userDB+';PWD='+password)
        return conexion
    except Exception as e:
        print("Ocurrió un error al conectarse a la base de datos: ", e)
        return None


@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    conexion = connect_to_database()
    if conexion is not None:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM Usuarios WHERE Correo_Electronico = ? AND Password = ?", (email, password))
        user = cursor.fetchone()
        if user is not None:
            session['user_id'] = user.ID  
            return redirect(url_for('home'))
        else:
            return "Invalid email or password"
    else:
        return "Failed to connect to the database"

@app.route('/configurar', methods=['POST'])
def configurar():
    moneda_defecto = request.form['moneda_defecto']
    tipo_tasa_interes_defecto = request.form['tipo_tasa_interes_defecto']
    tiempo_tasa_interes = request.form['tiempo_tasa_interes']

    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        UPDATE Configuracion
        SET Moneda_Defecto = ?, Tipo_Tasa_Interes_Defecto = ?, Tiempo_Tasa_Interes = ?
        WHERE Usuarios_ID = ?
    """, (moneda_defecto, tipo_tasa_interes_defecto, tiempo_tasa_interes, session['user_id']))

    conexion.commit()
    conexion.close()

    return 'La configuración ha sido actualizada exitosamente.'

@app.route('/configuracion', methods=['GET'])
def configuracion():
    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT Moneda_Defecto, Tipo_Tasa_Interes_Defecto, Tiempo_Tasa_Interes
        FROM Configuracion
        WHERE Usuarios_ID = ?
    """, (session['user_id'],))
    configuracion = cursor.fetchone()

    conexion.close()

    return render_template('configuracion.html', configuracion=configuracion)

@app.route('/Calculadora')
def Calculadora():    
    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT Moneda_Defecto, Tipo_Tasa_Interes_Defecto, Tiempo_Tasa_Interes
        FROM Configuracion
        WHERE Usuarios_ID = ?
    """, (session['user_id'],))
    configuracion = cursor.fetchone()

    conexion.close()
    return render_template('calculadora.html', configuracion=configuracion)

@app.route('/home')
def home():
    return render_template('botones.html')

@app.route('/registerer', methods=['GET', 'POST'])
def registerer():
    return render_template('register.html')

@app.route('/detalles_cuenta')
def detalles_cuenta():
    conexion = connect_to_database()
    if conexion is not None:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM Clientes WHERE Usuarios_ID = ?", session['user_id'])
        detalles = cursor.fetchall()
        return render_template('detalles_cuenta.html', detalles=detalles)
    else:
        return render_template('detalles_cuenta.html', detalles=None)


@app.route('/calcular', methods=['POST'])
def calcular():
    dix = 0
    if 'tipo_periodo[]' in request.form:
        dix = 1
        tipos_periodo = request.form.getlist('tipo_periodo[]')
        fechas_inicio_gracia = request.form.getlist('fecha_inicio_gracia[]')
        fechas_fin_gracia = request.form.getlist('fecha_fin_gracia[]')

    monto = float(request.form['monto'])
    tasa = float(request.form['tasa'])/100
    tasax = float(request.form['tasa'])
    tipo_tasa = request.form['tipo_tasa']
    periodo = request.form['tiempo_tasa_interes']
    fecha_inicial = request.form['fecha_inicial']
    fecha_final = request.form['fecha_final']
    moneda = request.form['moneda']
    pagos_anuales = int(request.form['pagos_anuales'])

    fecha_inicial = datetime.strptime(fecha_inicial, '%Y-%m-%d')
    fecha_final = datetime.strptime(fecha_final, '%Y-%m-%d')

    numero_pagos = pagos_anuales * (fecha_final.year - fecha_inicial.year)

    if periodo == 'Semestral':
        tasa /= 2
    elif periodo == 'Trimestral':
        tasa /= 4
    elif periodo == 'Bimestral':
        tasa /= 6
    elif periodo == 'Mensual':
        tasa /= 12

    if tipo_tasa == 'efectiva':
        tasa /= pagos_anuales
    else:  # nominal
        tasa = (1 + tasa/100)**(1/pagos_anuales) - 1

    cuota = monto * tasa / (1 - (1 + tasa)**(-numero_pagos))

    conexion = connect_to_database()
    cursor = conexion.cursor()

    prestamo_id = uuid.uuid4().int & (1<<31)-1 
    periodo_gracia_id = uuid.uuid4().int & (1<<31)-1 
    
    cursor.execute("""
        INSERT INTO Prestamos (ID, Clientes_ID, Tipo_Moneda, Tasa, Tipo_Tasa_Interes, Plazo_Pago, Fecha_inicio, Fecha_vencimiento)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (prestamo_id, session['user_id'], moneda, tasax, tipo_tasa, numero_pagos, fecha_inicial, fecha_final))
    
    if dix == 1:
        for tipo_periodo, fecha_inicio_gracia, fecha_fin_gracia in zip(tipos_periodo, fechas_inicio_gracia, fechas_fin_gracia):
                cursor.execute("""
                    INSERT INTO Periodos_de_Gracia (ID, Prestamos_ID, Tipo_de_periodo, Fecha_inicio, Fecha_fin)
                    VALUES (?, ?, ?, ?, ?)
                """, (periodo_gracia_id, prestamo_id, tipo_periodo, fecha_inicio_gracia, fecha_fin_gracia))
        
    cursor.execute("""
        SELECT *
        FROM Periodos_de_Gracia
        WHERE Prestamos_ID = ?
    """, (prestamo_id,))
    periodos_gracia = cursor.fetchall()

    for i in range(numero_pagos):
        Cuota_id = uuid.uuid4().int & (1<<31)-1 
        fecha_vencimiento = fecha_inicial + timedelta(days=i*365/pagos_anuales)
        monto_principal = cuota / (1 + tasa)**i
        monto_intereses = cuota - monto_principal

        if dix == 1: 
            for periodo in periodos_gracia:
                fecha_inicio_gracia = datetime.strptime(periodo.Fecha_inicio, '%Y-%m-%d')
                fecha_fin_gracia = datetime.strptime(periodo.Fecha_fin, '%Y-%m-%d')
                if fecha_inicio_gracia <= fecha_vencimiento <= fecha_fin_gracia:
                        if periodo.Tipo_de_periodo == 'total':
                            monto_principal = 0
                            monto_intereses = 0
                        elif periodo.Tipo_de_periodo == 'parcial':
                            monto_principal = 0
                            monto_intereses = cuota

            monto += monto_intereses

        cursor.execute("""
            INSERT INTO Cuotas (ID, Prestamos_ID, Numero_Cuotas, Fecha_Vencimiento, Monto_Principal, Monto_Intereses, Monto_Total_Cuota)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (Cuota_id, prestamo_id, i+1, fecha_vencimiento, monto_principal, monto_intereses, cuota))
    
    # ... rest of your code

    flujos_de_caja = [-monto] + [cuota] * numero_pagos
    VAN = npf.npv(tasa, flujos_de_caja)
    TIR = npf.irr(flujos_de_caja)

    # Controla la precisión de los decimales al imprimir los resultados
    
    TIRx = TIR * 100
    
    print(TIRx)
    
    indicadores_id = uuid.uuid4().int & (1<<31)-1 

    # Controla la precisión de los decimales al almacenar los resultados en la base de datos
    cursor.execute("""
        INSERT INTO Indicadores_Financieros (ID, Prestamos_ID, VAN, TIR)
        VALUES (?, ?, ?, ?)
    """, (indicadores_id, prestamo_id, round(VAN, 10), TIRx))
            
    conexion.commit()
    conexion.close()

    return redirect(url_for('cuotas2', prestamo_id=prestamo_id))

@app.route('/eliminar_prestamo', methods=['POST'])
def eliminar_prestamo():
    prestamo_id = request.form['prestamo_id']

    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        DELETE FROM Periodos_de_Gracia
        WHERE Prestamos_ID = ?
    """, (prestamo_id,))

    cursor.execute("""
        DELETE FROM Indicadores_Financieros
        WHERE Prestamos_ID = ?
    """, (prestamo_id,))

    cursor.execute("""
        DELETE FROM Cuotas
        WHERE Prestamos_ID = ?
    """, (prestamo_id,))

    cursor.execute("""
        DELETE FROM Prestamos
        WHERE ID = ?
    """, (prestamo_id,))

    conexion.commit()
    conexion.close()

    return redirect(url_for('prestamos'))


@app.route('/register', methods=['POST'])
def register():
    email = request.form['email']
    password = request.form['password']
    nombre = request.form['nombre']
    apellido = request.form['apellido']
    dni = request.form['dni']
    telefono = request.form['telefono']
    direccion = request.form['direccion']

    id_usuarios = uuid.uuid4().int & (1<<31)-1  

    conexion = connect_to_database()
    if conexion is not None:
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM Usuarios WHERE Correo_Electronico = ?", (email,))
        user = cursor.fetchone()
        if user is None:
            cursor.execute("INSERT INTO Usuarios (ID, Correo_Electronico, Password) VALUES (?, ?, ?)", (id_usuarios, email, password))
            cursor.execute("INSERT INTO Clientes (ID, Usuarios_ID, Nombre, Apellido, DNI, Telefono, Direccion) VALUES (?, ?, ?, ?, ?, ?, ?)", (id_usuarios, id_usuarios, nombre, apellido, dni, telefono, direccion))
            id_configuracion = uuid.uuid4().int & (1<<31)-1  
            cursor.execute("INSERT INTO Configuracion (ID, Usuarios_ID, Moneda_Defecto, Tipo_Tasa_Interes_Defecto, Tiempo_Tasa_Interes) VALUES (?, ?, ?, ?, ?)", (id_configuracion, id_usuarios, "Nuevo Sol", "Efectiva", "Anual"))
            conexion.commit()
            return render_template('index.html', prestamos=prestamos)
        else:
            return "Email already registered"
    else:
        return "Failed to connect to the database"

@app.route('/prestamos', methods=['GET'])
def prestamos():
    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM Prestamos
        WHERE Clientes_ID = ?
    """, (session['user_id'],))
    prestamos = cursor.fetchall()

    conexion.close()
    return render_template('prestamos.html', prestamos=prestamos)

@app.route('/cuotas2', methods=['GET'])
def cuotas2():
    prestamo_id = request.args.get('prestamo_id')

    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM Cuotas
        WHERE Prestamos_ID = ?
        ORDER BY Numero_Cuotas
    """, (prestamo_id,))
    cuotas = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM Indicadores_Financieros
        WHERE Prestamos_ID = ?
    """, (prestamo_id,))
    indicadores = cursor.fetchone()

    conexion.close()

    return render_template('cuotas.html', cuotas=cuotas, indicadores=indicadores)

@app.route('/cuotas', methods=['POST'])
def cuotas():
    prestamo_id = request.form['prestamo_id']

    conexion = connect_to_database()
    cursor = conexion.cursor()

    cursor.execute("""
        SELECT *
        FROM Cuotas
        WHERE Prestamos_ID = ?
        ORDER BY Numero_Cuotas
    """, (prestamo_id,))
    cuotas = cursor.fetchall()

    cursor.execute("""
        SELECT *
        FROM Indicadores_Financieros
        WHERE Prestamos_ID = ?
    """, (prestamo_id,))
    indicadores = cursor.fetchone()

    conexion.close()

    return render_template('cuotas.html', cuotas=cuotas, indicadores=indicadores)




if __name__ == '__main__':
    app.run()

