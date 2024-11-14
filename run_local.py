from api.index import app

if __name__ == '__main__':
    app.run(debug=True, port=3010)

#python3 run_local.py -e .env