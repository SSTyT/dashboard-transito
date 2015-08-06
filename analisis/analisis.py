#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlalchemy
import MySQLdb
from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
import json
import requests 
import datetime
import dateutil.parser
import multiprocessing

import anomalyDetection

detection_params_fn = "detection_params.json"


Base = declarative_base()
class Historical(Base):
    __tablename__ = 'historical'
    id = Column(Integer, primary_key=True)
    segment = Column(Integer, nullable=False)
    data = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False)

class Anomaly(Base):
    __tablename__ = 'anomaly'
    id = Column(Integer, primary_key=True)
    id_segment = Column(Integer, nullable=False)
    timestamp_start = Column(DateTime, nullable=False)
    timestamp_end = Column(DateTime, nullable=False)
    causa = Column(String(140), nullable=False)
    causa_id = Column(Integer, nullable=False)

class SegmentSnapshot(Base):
    __tablename__ = 'segment_snapshot'
    id = Column(Integer, primary_key=True)  
    timestamp_medicion = Column(DateTime, nullable=False)
    tiempo = Column(Integer, nullable=False)
    velocidad = Column(Float, nullable=False)
    causa = Column(String(140), nullable=False)
    causa_id = Column(Integer, nullable=False)
    duracion_anomalia = Column(Integer, nullable=False)
    indicador_anomalia = Column(Float, nullable=False)
    anomalia = Column(Integer, nullable=False)


def getData(url) :
    print url
    try :
        return requests.get(url).json()
    except :
        return None


"""
Funcion que arme para bajar datos de la api de teracode
Ej:
sensor_ids = [...] # Sacar de waypoints.py
download_startdate = "2015-07-01T00:00:00-00:00"
download_enddate = "2015-07-12T00:00:01-00:00"
step = datetime.timedelta(days=2)
newdata = downloadData (sensor_ids, step, download_startdate, download_enddate, outfn="raw_api_01_11.json")
"""
def downloadData (sensor_ids, step, download_startdate, download_enddate, outfn=None, token="superadmin.") :    
    pool = multiprocessing.Pool(5)
    #vsensids = virtsens["id_sensor"].unique()
    urltpl = "https://apisensores.buenosaires.gob.ar/api/data/%s?token=%s&fecha_desde=%s&fecha_hasta=%s"
    
    end = dateutil.parser.parse(download_enddate)
    urls = []
    for sensor_id in sensor_ids :
        start = dateutil.parser.parse(download_startdate)
        while start <= end :
            startdate, enddate = start, start + step
            print startdate, enddate, sensor_id
            url = urltpl % (sensor_id, token, startdate.strftime("%Y-%m-%dT%H:%M:%S-03:00"), enddate.strftime("%Y-%m-%dT%H:%M:%S-03:00"))
            urls += [url]
            start += step
    
    #alldata = map(getData, urls)
    alldata = pool.map(getData, urls)
    pool.close()
    pool.terminate()
    pool.join()
    if outfn != None :
        outf = open(outfn,"wb")
        json.dump(alldata, outf)
        outf.close()
    
    return alldata


def createDBEngine () :
    #engine = sqlalchemy.create_engine("postgres://postgres@/postgres")
    # engine = sqlalchemy.create_engine("sqlite:///analysis.db")
    if os.environ.get('OPENSHIFT_MYSQL_DIR'):
        host = os.environ.get('OPENSHIFT_MYSQL_DB_HOST')
        user = os.environ.get('OPENSHIFT_MYSQL_DB_USERNAME')
        password = os.environ.get('OPENSHIFT_MYSQL_DB_PASSWORD')
        engine = sqlalchemy.create_engine("mysql://"+user+":"+password+"@"+host+"/dashboardoperativo")
        return engine
    else:
        user = config.mysql['user']
        password = config.mysql['password']
        host = config.mysql['host']
        db = config.mysql['db']
        engine = sqlalchemy.create_engine("mysql://"+user+":"+password+"@"+host+"/"+db)
        return engine

def getDBConnection () :
    conn = createDBEngine().connect()
    return conn

def setupDB () :
    engine = createDBEngine()
    Base.metadata.create_all(engine)
 
"""
Baja datos de nuevos de teracode y los guarda en la tabla "historical"
"""
def updateDB(data) : 
    conn = getDBConnection()
    # parsear json
    Session = sessionmaker(bind=conn)
    session = Session()
    # loopear por cada corredor
    for corredor in data:
        if corredor:
            for segmento in corredor["datos"]["data"]:
                print segmento
                # crear nueva instancia de Historical
                segment = segmento["iddevice"]
                data = segmento["data"]
                timestamp = datetime.datetime.strptime(segmento["date"], '%Y-%m-%dT%H:%M:%S-03:00')
                segmentdb = Historical(**{
                    "segment" : segment,
                    "data" : data,
                    "timestamp" : timestamp
                    })
                # pushear instancia de Historial a la base
                session.add(segmentdb)
                session.commit()
        else:
            continue
    
    
"""
Elimina registros con mas de un mes de antiguedad de la tabla "historical"
"""
def removeOldRecords() :
    pass

"""
Este loop se va a ejecutar con la frecuencia indicada para cada momento del dia.
"""
def executeLoop(desde, hasta) :
    """
        traer los sensores lista de archivo configuracion
        desde = "2015-07-01T00:00:00-00:00"
        hasta = "2015-07-12T00:00:01-00:00"        
    """
    sensores = [10,12,57, 53,51,49, 40, 43, 37,36, 21, 31,33,35, 13,14, 18,17,23, \
    24,25, 26,28, 30,32 ,45, 47, 38, 44, 48,48, 11,56, 54,55, 41, 22, 16,15, 19, 20, 10, 27,29, 34, 39, 42, 46, 50 ,52]
    
    newrecords = downloadData(sensores, datetime.timedelta(days=2), desde, hasta)
    updateDB(newrecords)
    if newrecords : 
        performAnomalyAnalysis()

"""
Esta tabla retorna una lista de tuplas de la forma (id_segment, data, timestamp) con los ultimos registros agregados a la tabla "historical"
"""
def getLastRecords() :
    pass

"""
Esta tabla retorna una lista de tuplas de la forma (id_segment, data, timestamp) con todos los registros agregados a la tabla "historical" en el ultimo mes
"""
def getLastMonthRecords() :
    pass

"""
Esta funcion determina los parametros de deteccion de anomalias para cada segmento y los guarda en el archivo detection_params.json
"""
def updateDetectionParams() :
    lastmonthrecords = getLastMonthRecords()
    newparams = anomalyDetection.computeDetectionParams(lastmonthrecords)
    outf = open(detection_params_fn, "wb")
    outf.write(newparams)
    outf.close()

"""
Esta funcion retorna la data que se va a cargar en la tabla segment_snapshot como una lista de diccionarios.
Recibe:
- Una lista con las anomalias encontradas de la forma:
[{'timestamp': datetime.datetime(2015, 7, 12, 6, 0), 'indicador_anomalia': 2.29, 'id_segment': 10}]
- Un listado de tuplas de la forma (id_segment, data, timestamp) con los datos de los ultimos 20 minutos

Retorna:
- Una lista con un dict tipo json por cada segmento con su estado updateado para la tabla segment_snapshot.
  Deberia tener la siguiente estructura:
{
    "id" : (id del segmento),
    "timestamp_medicion" : (timestamp de la medicion),
    "tiempo" : (tiempo que toma atravesar el segmento segun la ultima medicion),
    "velocidad" : (distancia del corredor / tiempo),
    "causa" : (por ahora null, lo modifica la UI),
    "causa_id" : (por ahora null, lo modifica la UI),
    "duracion_anomalia" : (por ahora null),
    "indicador_anomalia" : (porcentaje),
    "anomalia" : True/False
}
"""
# TODO: Completar campos "velocidad" y "duracion_anomalia"
def getCurrentSegmentState (anomalies, lastrecords) :
    segments = {}
    for r in lastrecords :
        if not segments.has_key(r[0]) or r[2] > segments[r[0]][2] :
            segments[r[0]] = r
    
    ad = { a["id_segment"] : a for a in anomalies }
    
    output = []
    for s in segments.values() :
        output += [{
            "id" : s[0],
            "timestamp_medicion" : s[2],
            "tiempo" : s[1],
            "velocidad" : -1, #s["data"] / s["id_segment"],
            "causa" : "",
            "causa_id" : 0,
            "duracion_anomalia" : 0,
            "indicador_anomalia" : ad.get(s[0], {}).get("indicador_anomalia", 0),
            "anomalia" : ad.has_key(s[0]),
        }]
    return output

"""
Lee los parametros de deteccion de la tabla detection_params.csv
"""
def getDetectionParams() :
    return open(detection_params_fn).read()
  
"""
Updetea una anomalia prexistente
La entrada de esta funcion es un unico diccionario que identifica a la anomalia y tiene la siguiente forma:
{
    "id_segment" : N,
    "timestamp" : N,
    "causa" : N,
    "causa_id" : N
    "timestamp_end" : N,
}
Los atributos id_segment y timestamp se usan para determinar si una anomalia ya esta presente en la tabla "anomaly".
Si no esta presente la funcion falla
Si el atributo causa, causa_id y/o timestamp_end estan presentes se updetea dicho campo en el registro de esa anomalia.
"""
def upsertAnomalies (newanomalydata) :
    pass
    
def updateSnapshot(curstate):
    pass

def performAnomalyAnalysis() :
    lastrecords = getLastRecords()
    detectparams = getDetectionParams()
    anomalies = anomalyDetection.detectAnomalies(detectparams, lastrecords)
    upsertAnomalies(anomalies)
    curstate = getCurrentSegmentState(anomalies, lastrecords)
    updateSnapshot(curstate)
    
def dailyUpdate () :
    removeOldRecords()
    updateDetectionParams()


if __name__ == '__main__':

    setupDB()
