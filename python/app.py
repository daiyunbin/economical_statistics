import os
import pickle

import pandas as pd
from flask import Flask, render_template, request, redirect
from database import Database
from add_to_dictionary import *
from analysis import sentence_info

app = Flask(__name__)


@app.route("/")
def hello():
    return render_template('index.html')


@app.route("/companies")
@app.route("/companies/<company>")
def companies(company=None):
    db = Database()
    coefs = None
    pvalues = None
    if company is None:
        cs = db.get_all_companies()
    else:
        cs = db.get_company_by_id_with_price(company)
        with open('./../data/companies.pickle', 'rb') as f:
            companies = pickle.load(f)
        l = list(filter(lambda c: c["ticker"] == cs[0]["ticker"], companies))
        if len(l) > 0:
            c = l[0]
            coefs = c["coef"]
            pvalues = c['pvalues']
        else:
            coefs = None
            pvalues = None
    return render_template('companies.html', companies=cs, coefs=coefs, pvalues=pvalues)


@app.route("/news")
@app.route("/news/<n>")
def news(n=None):
    db = Database()
    info = None
    if n is None:
        ns = db.get_all_news()
    else:
        ns = db.get_news_by_id(n)
        with open('./../data/news_' + str(n) + '_words', 'rb') as f:
            info = pickle.load(f)
    return render_template('news.html', news=ns, info=info)


@app.route("/dict", methods=["GET", "POST"])
def dict():
    if request.method == 'POST':
        f = request.files['file']
        type = request.form['type']
        if type == 'positive':
            f.save('./positive.txt')
            positive_from_txt('./positive.txt')
        elif type == 'negative':
            f.save('./negative.txt')
            negative_from_txt('./negative.txt')
        return redirect('/dict')
    else:
        percents = None
        if os.path.exists('./../data/result.pickle'):
            with open('./../data/result.pickle', 'rb') as f:
                percents = pickle.load(f)
        percents['values'] = sorted(percents['values'], key=lambda p: p["percent"])
        db = Database()
        db.db.execute("""
            SELECT * FROM words ORDER BY id DESC
        """)
        dict = db.db.fetchall()
        if os.path.exists('./is_parsing'):
            with open('./is_parsing', 'r') as f:
                if f.read() == '1':
                    status = 'parsing'
                else:
                    status = 'not parsing'
        else:
            status = 'not parsing'
        with open("./../data/word_cloud_data", "rb") as f:
            words = pickle.load(f)
        return render_template('dict.html', dict=dict, status=status, percents=percents, all_words=words[0],
                               pos_words=words[1], neg_words=words[2])


@app.route("/delete", methods=["POST"])
def delete():
    if request.method == "POST":
        db = Database()
        id = request.form["id"]
        db.db.execute("""DELETE FROM words WHERE id = %s""", (id,))
        db.connection.commit()
        return redirect('/dict')
    else:
        return ''


@app.route("/reparse", methods=["POST"])
def reparse():
    if request.method == "POST":
        if os.path.exists('./is_parsing'):
            with open('./is_parsing', 'r') as file:
                if int(file.read()) != 1:
                    with open('./is_parsing', 'w') as file:
                        file.write(str(1))
                    with open('./need_parsing', 'w') as file:
                        file.write(str(1))
                    return 'Parsing started'
                else:
                    return 'Already parsing'
        else:
            with open('./is_parsing', 'w') as file:
                file.write(str(1))
            with open('./need_parsing', 'w') as file:
                file.write(str(1))
            return 'Parsing started'
    else:
        return ''


@app.route('/history')
@app.route('/history/<page>')
def history(page=0):
    df = pd.read_csv('./../data/news_with_one_company_sent_scores.csv')
    df_dict = df.to_dict(orient='rows')
    page = int(page)
    ns = df_dict[page * 10:page * 10 + 10]
    for i in range(0, len(ns)):
        ns[i]["info"] = sentence_info(ns[i]["text"])
        ns[i]["id"] = page * 10 + i
    return render_template("news_history.html", news=ns, page=page)


@app.route('/predictions')
def predictions():
    db = Database()
    db.db.execute("""SELECT * FROM companies""")
    companies = db.db.fetchall()
    predictions = list()
    tr = 0
    l = 0
    with open("./../data/companies.pickle", 'rb') as c_file:
        companies_from_file = pickle.load(c_file)
    for c in companies:
        db.db.execute("""
            SELECT predictions.prediction,actual,time,current, updated_at,predictions.id,companies.name FROM predictions INNER JOIN companies ON predictions.company_id = companies.id WHERE predictions.company_id=%s ORDER BY predictions.id DESC LIMIT 1  
        """, (c["id"],))
        prediction = db.db.fetchone()
        if prediction is None:
            continue
        prediction["trend"] = float(prediction["prediction"]) > float(prediction["current"])
        predictions.append(prediction)
        db.db.execute("""
            SELECT prediction, actual, current FROM predictions WHERE company_id = %s AND actual != 0
        """, (c["id"],))
        d = db.db.fetchall()
        prediction["count"] = len(d)
        prediction["true"] = 0
        for _d in d:
            first = _d["prediction"] > _d["current"]
            second = _d["actual"] > _d["current"]
            if first == second:
                prediction["true"] += 1
        if prediction["count"] == 0:
            prediction["percent"] = "0"
        else:
            prediction["percent"] = "{0:.2f}".format(prediction["true"] / prediction["count"] * 100)
        tr += prediction["true"]
        l += prediction["count"]
        if l == 0:
            perc = 0
        else:
            perc = "{0:.2f}".format(tr / l * 100)
        prediction["ma_percent"] = list(filter(
            lambda _c: ("name" in _c and _c["name"] == prediction["name"]) or (prediction["name"] in _c["parse_name"]),
            companies_from_file))[0]["ma_parcent"]
    predictions = sorted(predictions, key=lambda p: (float(p["percent"]), float(p["true"])), reverse=True)
    return render_template("predictions.html", predictions=predictions, tr=tr, l=l, perc=perc)


@app.route('/all_predictions')
@app.route('/all_predictions/<page>')
def all_predictions(page=0):
    page = int(page)
    db = Database()
    db.db.execute("""
            SELECT predictions.prediction,actual,current,time,updated_at,predictions.id,companies.name, companies.id as c_id FROM predictions INNER JOIN companies ON predictions.company_id = companies.id ORDER BY predictions.id DESC LIMIT %s OFFSET %s  
        """, (50, 50 * int(page)))
    predictions = db.db.fetchall()
    if predictions is None:
        return render_template("all_predictions.html", predictions=predictions)
    for i in range(len(predictions)):
        predictions[i]["trend"] = float(predictions[i]["prediction"]) > float(predictions[i]["current"])
    return render_template("all_predictions.html", predictions=predictions, page=page)


@app.route('/predict')
def predict():
    from parse import predict
    predict()
    return redirect('/predictions')


@app.route('/prediction/<id>')
def prediction(id):
    db = Database()
    db.db.execute("""
            SELECT predictions.*,companies.name,companies.ticker FROM predictions INNER JOIN companies ON predictions.company_id = companies.id WHERE predictions.id=%s ORDER BY predictions.id DESC LIMIT 1  
        """, (id,))
    p = db.db.fetchone()
    if p is None:
        return render_template("prediction.html", prediction=p)
    p["trend"] = float(p["prediction"]) > float(p["current"])
    with open('./../data/companies.pickle', 'rb') as f:
        companies = pickle.load(f)
    l = list(filter(lambda c: c["ticker"] == p["ticker"], companies))
    if len(l) > 0:
        c = l[0]
        coefs = c["coef"]
        pvalues = c['pvalues']
    else:
        coefs = None
        pvalues = None

    return render_template("prediction.html", prediction=p, coefs=coefs, pvalues=pvalues)


@app.route('/update_actual')
def update_actual():
    from update_actual import update_actual
    update_actual()
    return redirect('/predictions')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
