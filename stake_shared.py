import csv
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta, timezone

import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService

thresholds = [9, 19, 29, 59, 99, 199, 299, 499, 799, 999, 1299, 1499, 1999, 2499, 2999, 3999, 4999, 6999, 9999, 12999, 14999, 19999, 22999, 24999, 29999,
              34999, 39999, 49999, 59999, 69999, 79999, 99999, 119999, 149999, 199999, 249999, 299999]

BROWSER_PROFILE_DIR = os.getenv('BROWSER_PROFILE_DIR', '')
BROWSER_EXE_LOC = os.getenv('BROWSER_EXE_LOC', '')
GECKO_EXE_LOC = os.getenv('GECKO_EXE_LOC', '')
BROWSER_TYPE = os.getenv('BROWSER_TYPE', '')

db_config = {
    'host': os.getenv('MYSQL_HOST', ''),
    'user': os.getenv('MYSQL_USER', ''),
    'password': os.getenv('MYSQL_PASS', ''),
    'database': os.getenv('MYSQL_DB', '')
}

DEBUG_ENABLED = True
USE_DATABASE = True

logger = logging.getLogger()

def setup_logging(game_type):
    global logger
    logger = logging.getLogger(f'stake_{game_type}_logger')
    if not logger.hasHandlers():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', filename=f'stake_{game_type}.log', filemode='w')
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logger.addHandler(console_handler)
        logger.info(f'Starting stake_{game_type} logger (independent run)...')
    else:
        logger.info(f'Using existing stake_{game_type} logger...')
    return logger

def setup_browser():
    global logger
    logger.info("setup_browser....")
    if BROWSER_TYPE == 'FIREFOX':
        service = FirefoxService(GECKO_EXE_LOC)
        options = webdriver.FirefoxOptions()
        options.binary_location = BROWSER_EXE_LOC
        options.add_argument("--log-level=3")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        options.set_preference("browser.console.logLevel", "fatal")
        options.set_preference("webdriver.log.file", "NUL" if os.name == "nt" else "/dev/null")
        options.set_preference('dom.webnotifications.enabled', False)
        options.set_preference('media.peerconnection.enabled', True)
        options.set_preference("profile", BROWSER_PROFILE_DIR)
        # Comment to view
        # options.add_argument('--headless')
        # options.add_argument("--window-size=0,0")
        # options.add_argument("--window-size=1920,1080")
        driver = webdriver.Firefox(service=service, options=options)
        logger.info(driver.capabilities.get("moz:profile"))
        logger.info(f"Using {BROWSER_TYPE} driver.")
        return driver
    elif BROWSER_TYPE == 'CHROME':
        logger.info(f"Using {BROWSER_TYPE} driver.")
        service = ChromeService(GECKO_EXE_LOC)
        options = webdriver.ChromeOptions()
        options.binary_location = BROWSER_EXE_LOC
        options.add_argument("--log-level=3")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(service=service, options=options)
        logger.info(f"Using {BROWSER_TYPE} driver.")
        return driver
    else:
        logger.warning(f"Unknown {BROWSER_TYPE} driver.")
    return None

def load_existing_data(game_type, point_label):
    global logger
    logger.info("load_existing_data...")
    data = {}
    file_path = f'data/{game_type}_data.csv'
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as file:
                csv_reader = csv.reader(file)
                next(csv_reader)
                for row in csv_reader:
                    point, start_time = row
                    data[start_time] = {
                        point_label: float(point),
                        'startTime': start_time
                    }
        except Exception as e:
            logger.error(f"Error loading CSV: {e}. Retrying after sleep.")
            time.sleep(10)
            return load_existing_data(game_type, point_label)
    return data

def get_latested_from_mysql(game_type):
    global logger
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        query = f"SELECT start_time FROM stake_{game_type} ORDER BY start_time DESC LIMIT 1"
        cursor.execute(query)
        result = cursor.fetchone()
        return result[0] if result else None
    except mysql.connector.Error as err:
        logger.error(f"Error fetching most recent hash: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def get_latested_from_csv(game_type):
    global logger
    filepath = f'data/{game_type}_data.csv'
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
            if len(lines) < 2:
                return None
            last_line = lines[-1].strip()
            if not last_line:
                last_line = lines[-2].strip()
            _, start_time = last_line.split(',')
            return datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S')
    except Exception as e:
        logger.error(f"Error reading most recent time from CSV: {e}")
        return None

def insert_latest_mysql(game_type, point_label, records):
    global logger
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        insert_query = f"""
            INSERT INTO stake_{game_type} (hash_id, {point_label}, start_time)
            VALUES (%s, %s, %s)
        """
        for record_id, record in records.items():
            hash_id = record['id']
            point = record[point_label]
            start_time = datetime.strptime(record['startTime'], '%m/%d/%Y %H:%M:%S')
            cursor.execute(insert_query, (hash_id, point, start_time))
        connection.commit()
        logger.info(f"Inserted {len(records)} new records into the database")
    except mysql.connector.Error as err:
        logger.error(f"Error inserting data: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def insert_latest_csv(game_type, point_label, records):
    global logger
    logger.info("insert_latest_csv...")
    if records:
        try:
            csv_file = f'data/{game_type}_data.csv'
            with open(csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                if os.stat(csv_file).st_size == 0:
                    writer.writerow([point_label, 'startTime'])
                sorted_data = sorted(records.values(), key=lambda x: datetime.strptime(x['startTime'], '%m/%d/%Y %H:%M:%S'))
                for record in sorted_data:
                    writer.writerow([record[point_label], datetime.strptime(record['startTime'], '%m/%d/%Y %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%S')])
            logger.info(f"Appended {len(records)} new records to {csv_file}")
        except Exception as e:
            logger.error(f"Failed to append new data to CSV: {e}")

def export_mysql_to_csv(game_type, point_label):
    global logger
    output_file = f'data/{game_type}_data.csv'
    logger.info(f'export_mysql_to_csv {output_file}')
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        select_query = f"SELECT {point_label}, start_time FROM stake_{game_type} ORDER BY start_time ASC"
        cursor.execute(select_query)
        rows = cursor.fetchall()
        with open(output_file, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow([point_label, 'startTime'])
            for row in rows:
                point, start_time = row
                formatted_time = start_time.strftime('%Y-%m-%dT%H:%M:%S')
                csv_writer.writerow([point, formatted_time])
        logger.info(f"Data exported successfully to {output_file}")
    except mysql.connector.Error as err:
        logger.info(f"Error: {err}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def analyze_high_points(game_type, point_label, threshold, all_data):
    global logger
    logger.info("analyze_high_points...")
    sorted_records = sorted(all_data.values(), key=lambda x: datetime.strptime(x['startTime'], '%Y-%m-%dT%H:%M:%S'), reverse=True)
    results = []
    previous_time = None
    latest_index = None
    for index, record in enumerate(sorted_records):
        if record[point_label] > threshold:
            start_time = datetime.strptime(record['startTime'], '%Y-%m-%dT%H:%M:%S')
            if previous_time:
                records_between = index - previous_index
                time_since_previous = previous_time - start_time
                results[-1]['records_since_previous'] = records_between
                results[-1]['time_since_previous'] = str(time_since_previous)
            else:
                time_since_previous = timedelta(0)
            results.append({
                point_label: record[point_label],
                'startTime': record['startTime'],
                'records_since_previous': 0,
                'time_since_previous': str(time_since_previous)
            })
            previous_index = index
            previous_time = start_time
            if latest_index is None:
                latest_index = index
    total_records = len(sorted_records)
    latest_index = total_records - latest_index - 1 if latest_index is not None else 0
    if results:
        latest_time = datetime.strptime(results[0]['startTime'], '%Y-%m-%dT%H:%M:%S')
        logger.info(f"High {game_type.capitalize()}points (>{threshold}): {len(results)} | RecordsSinceLatest: {total_records - latest_index} | TimeSinceLatest: {datetime.now() - latest_time}")
    else:
        logger.info(f"No records over threshold {threshold}")

    maxcount = 500
    counter = 0
    if results:
        for item in results:
            counter += 1
            logger.info(f"{point_label.capitalize()}: {item[point_label]} At Time: {item['startTime']} | RecordsSincePrevious: {item['records_since_previous']} | TimeSincePrevious: {item['time_since_previous']}")
            if counter > maxcount:
                break

    with open(f'data/over{threshold}{game_type}.json', 'w') as file:
        json.dump(results[:500], file, indent=4)

def adjust_time(gmt_time_str):
    gmt_time = datetime.strptime(gmt_time_str, '%a, %d %b %Y %H:%M:%S %Z').replace(tzinfo=timezone.utc)
    offset = timedelta(hours=4) if is_dst(gmt_time) else timedelta(hours=5)
    return (gmt_time - offset).strftime('%m/%d/%Y %H:%M:%S')

def is_dst(dt):
    year = dt.year
    dst_start = datetime(year, 3, 8, 2) + timedelta(days=(6 - datetime(year, 3, 8).weekday()))
    dst_end = datetime(year, 11, 1, 2) + timedelta(days=(6 - datetime(year, 11, 1).weekday()))
    return dst_start <= dt.replace(tzinfo=None) < dst_end

def run_stake_game(game_type):
    global logger
    logger = setup_logging(game_type)
    logger.info(f'Starting {game_type} process...')
    point_label = "crashpoint" if game_type == "crash" else "slidepoint"
    point_label_alt = "crashpoint" if game_type == "crash" else "multiplier"
    query_outer_name = "crashGameList" if game_type == "crash" else "slideList"
    query_name = "crashGameList" if game_type == "crash" else "slideGameList"
    browser_driver = setup_browser()
    driver_service = browser_driver.service
    new_data = {}
    if USE_DATABASE:
        latest_starttime = get_latested_from_mysql(game_type)
    else:
        latest_starttime = get_latested_from_csv(game_type)
    latest_starttime = latest_starttime.strftime('%m/%d/%Y %H:%M:%S')
    logger.info(f"Most recent StartTime in database: {latest_starttime}")
    try:
        with browser_driver as driver:
            driver.get(f'https://stake.us/casino/games/{game_type}')
            time.sleep(5)
            if DEBUG_ENABLED:
                logger.info(f"Checking {game_type} data...")
            cookies = browser_driver.get_cookies()
            cookie_str = '; '.join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
            escaped_cookie_str = cookie_str.replace('"', '\\"')
            offset = 0
            limit = 50
            while offset < 900:
                query = f"""
                    query {query_outer_name}History($limit: Int, $offset: Int) {{
                        {query_name}(limit: $limit, offset: $offset) {{
                            id
                            startTime
                            {point_label_alt}
                            hash {{ 
                                id 
                                hash 
                                __typename 
                            }}
                            __typename
                        }}
                    }}
                """
                script = f"""
                    return fetch("https://stake.us/_api/graphql", {{
                        method: "POST",
                        headers: {{
                            "Content-Type": "application/json",
                            "Accept": "application/graphql+json, application/json",
                            "Cookie": "{escaped_cookie_str}"
                        }},
                        body: JSON.stringify({{
                            query: `{query}`,
                            variables: {{
                                "limit": {limit},
                                "offset": {offset}
                            }}
                        }})
                    }}).then(response => response.json());
                """
                if DEBUG_ENABLED:
                    logger.info(f"Script -> {script}")
                response_data = browser_driver.execute_script(script)
                if DEBUG_ENABLED:
                    logger.info(f"Fetched {game_type} game data: {response_data}")
                game_list = response_data['data'][query_name]
                if not game_list:
                    break
                for game in game_list:
                    game_id = game['id']
                    if game_type == "slide" and 'multiplier' in game:
                        game['slidepoint'] = game.pop('multiplier')
                    game['startTime'] = datetime.strptime(adjust_time(game['startTime']), '%m/%d/%Y %H:%M:%S').strftime('%m/%d/%Y %H:%M:%S')
                    gameStartTime = game['startTime']
                    if latest_starttime and gameStartTime == latest_starttime:
                        logger.info("Reached latest stored record.")
                        break
                    new_data[game_id] = game
                if gameStartTime == latest_starttime:
                    break
                offset += limit
                time.sleep(random.uniform(1, 3))
    except KeyboardInterrupt:
        if DEBUG_ENABLED:
            logger.info("Monitoring stopped by user")
        if browser_driver:
            browser_driver.quit()
            logger.info("Browser session closed on user interrupt.")
    except Exception as e:
        logger.error(f"Error in main monitoring loop: {e}")
    finally:
        if browser_driver:
            try:
                browser_driver.quit()
                logger.info("Browser session closed successfully.")
            except Exception as e:
                logger.error(f"Error while quitting driver: {e}")
        if driver_service:
            try:
                driver_service.stop()
                logger.info("Selenium service stopped successfully.")
            except Exception as e:
                logger.error(f"Error while stopping Selenium service: {e}")
    if new_data:
        if USE_DATABASE:
            insert_latest_mysql(game_type, point_label, new_data)
            filepath = f'data/{game_type}_data.csv'
            if not os.path.exists(filepath):
                export_mysql_to_csv(game_type, point_label)
                new_data = None
    insert_latest_csv(game_type, point_label, new_data)
    all_data = load_existing_data(game_type, point_label)
    for threshold in thresholds:
        analyze_high_points(game_type, point_label, threshold, all_data)
    log_path = os.path.join(os.getcwd(), "geckodriver.log")
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
            if DEBUG_ENABLED:
                logger.info("Deleted geckodriver.log")
        except Exception as e:
            logger.error(f"Failed to delete geckodriver.log: {e}")
    logger.info(f'Stopping {game_type} process...')
