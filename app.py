
import boto3
import csv
import io
import os
import re
import statistics
from collections import Counter

from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)
# S3 Bucket Names
UPLOAD_BUCKET = "s3-cw-input" # Replace with your upload
DATA_BUCKET = "s3-cw-output" # Replace with your data

s3 = boto3.client('s3')

stopwords = [ "the", "and", "a", "an", "in", "on", "at", "to", "is", "are", "of", "for", "with", "that", "this", "it"]
token_re = re.compile(r"\b[\w']+\b", re.UNICODE)
sentence_stop = re.compile(r'[.!?]+')

def read_text_file(bucket, key):
        obj = s3.get_object(Bucket=bucket, Key=key)
        text = obj['Body'].read().decode('utf-8')
        return text


def frequent_words(filename, top_words=20, stop_words=stopwords):
        with open(filename, "r", encoding="utf-8") as f:
                text = f.read()
        words = token_re.findall(text.lower())
        filtered = [w for w in words if w not in stop_words]
        counter = Counter(filtered)
        return counter.most_common(top_words)

def start_words(filename, top_words=10):
        with open(filename, "r", encoding="utf-8") as f:
                text = f.read()
        sentences = [s.strip() for s in sentence_stop.split(text) if s.strip()]
        starters = []

        for s in sentences:
                words = token_re.findall(s)
                if words:
                        starters.append(words[0].lower())

        counter = Counter(starters)
        return counter.most_common(top_words)


def sentence_length(filename):
        with open(filename, "r", encoding="utf-8") as f:
                text = f.read()
        sentences = [s.strip() for s in sentence_stop.split(text) if s.strip()]
        lengths = [len(token_re.findall(s)) for s in sentences]

        if not lengths:
                return {"mean": 0, "median": 0, "stdev": 0}

        return {
                "mean": statistics.mean(lengths),
                "median": statistics.median(lengths),
                "stdev": statistics.pstdev(lengths)
        }


def write_sentence_stats_to_csv(results, bucket, key):
        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["Metric", "Value"])

    # Writer for Frequent words
        writer.writerow([])
        writer.writerow(["Top Frequent Words", "Count"])
        for w, c in results["frequent_words"]: # for loop for each word in the results
                writer.writerow([w, c])

    # Starting words
        writer.writerow([])
        writer.writerow(["Sentence Starting Words", "Count"])
        for w, c in results["start_words"]:
                writer.writerow([w, c])

    # Sentence lengths
        writer.writerow([])
        writer.writerow(["Sentence Length Statistics", "Value"])
        for k, v in results["sentence_length"].items():
                writer.writerow([k, v])

        s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=output.getvalue().encode("utf-8")
                )



@app.route("/", methods=["GET", "POST"])
def upload_file():
        if request.method == "POST":
                if 'file' not in request.files:
                        return "No file part"
                file = request.files['file']
                if file.filename == '':
                        return "No selected file"
                try:
                        s3.upload_fileobj(file, UPLOAD_BUCKET, file.filename)
                        text = read_text_file(UPLOAD_BUCKET, file.filename)
                        results = {
                                "frequent_words": frequent_words(text),
                                "start_words": start_words(text),
                                "sentence_length": sentence_length(text)
                                }

            # Save results CSV to output bucket
                        result_key = "sentence_stats.csv"
                        write_sentence_stats_to_csv(results, DATA_BUCKET, result_key)
                        return redirect(url_for("view_data"))
                except Exception as e:
                        return f"Error uploading file: {e}"
        return render_template("upload.html")

@app.route("/process", methods=["POST"])
def process():
        file = request.files["file"]
        filepath = "/tmp/"+file.filename
        file.save(filepath)

        selected = request.form.getlist("analysis") # gets the list of selected functions
        results = {}

        if "frequent_words" in selected:
                results["frequent_words"]=frequent_words(filepath)
        if "start_words" in selected:
                results["start_words"]= start_words(filepath)
        if "sentence_length" in selected:
                results["sentence_length"] = sentence_length(filepath)
        return results

@app.route("/data")
def view_data():
        try:
                data_key = "sentence_stats.csv" # Replace with your CSV
                obj = s3.get_object(Bucket=DATA_BUCKET, Key=data_key)
# Read CSV data directly using the csv module
                csv_data = obj['Body'].read().decode('utf-8')
                reader = csv.DictReader(io.StringIO(csv_data)) # Use DictReader

                rows = list(reader)
                return render_template("data.html", table=rows)

        except Exception as e:
                return f"Error reading CSV file: {e}", 500
if __name__ == "__main__":
        app.run(debug=True, host='0.0.0.0', port='8080')
