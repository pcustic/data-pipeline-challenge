# Veryfi Challenge - Data

This is my submission for a Veryfi data interview challenge. 

In short, the task was following:

> Suppose that Veryfi is building a database of products that may appear on customer receipt
scans. There is no official database of products; Veryfi has to build it from various data sources.
> 
> The dataset includes a sample of 50,000 products in .json format from a website called
openfoodfacts.com, which crowdsources its information and is publicly available.
> 
> This data will eventually be consumed by an AI algorithm that compares the receipt to the
database of products and assigns a likely match. The product data will primarily be consumed by
the algorithm, but may also be presented to customers.
> 
> Task:
> 1. Build a pipeline that will ingest this dataset into a database.
>   1. The code should assume that similar datasets will be received regularly from this
source; approximately weekly
>   2. You should design a unified internal schema that will be able to merge with other
data sources.
>   3. You may use the “code” field as a primary key
> 2. Build this with scalable ETL in mind.



## Solution

![Architecture diagram](/images/diagram.png)

Above is shown the diagram of the architecture of the whole pipeline.

The pipeline consists of several parts:
1. API built with [FastAPI](https://fastapi.tiangolo.com/) framework
2. FileSplitter Python service
3. DataProcessor Python service
4. [MongoDB](https://www.mongodb.com/) database
5. [RabbitMQ](https://rabbitmq.com/) queues 


### Pipeline process
The API is the entrypoint to the pipeline. It is implemented in FastAPI framework, and it exposes several endpoints, 
most important being the `/upload`. Through it, you upload json data files to be processed (as `multipart/form-data`).

The endpoint doesn't actually process the file. It takes the uploaded file and saves it on an internal storage. It then
saves an `UploadedFile` record in Mongo database with basic info such as filename, location, etc. 
After that, it sends a message to a `files_uploaded` queue on RabbitMQ. That message is used as a signal that new file
was uploaded and that it needs to be processed.

> Quick side note: I decided not to have `/upload` actually process the file, so we can return the response to the user
> as soon as possible. Files for processing can be really large and processing could take a long time. For these
> kind of situations it is better to have some other service to process the file. 

**FileSplitter** is the service that is listening to the messages on the `files_uploaded` queue. Those messages
contain the location of the uploaded file. FileSplitter service then reads the uploaded file from that location in
chunks (so we don't have the whole file in memory) and groups items from files into batches (currently of 100 records).
When each batch is created, the service packs that batch into a new message and sends it to `data_processing` queue on
RabbitMQ. After the whole file is read, the service updates the `UploadedFile` record with count of total records 
found in the file. That is used later to track if we have processed the whole file.

**DataProcessor** is the service that is listening to the messages on the `data_processing` queue. Those messages
contain actual items that needs to be saved to the database. To each item we add two fields: `file_id` - id of the file
from which the record is extracted and `last_modified_at_veryfi` - which states datetime of the insertion/update in
our system. We use the `code` key from the item as a key by which we uniquely determine each item. The service upserts
each record, i.e. updates a record if there is already a record with the same `code`, otherwise inserts it into the DB.

Base of the record that is inserted into database looks like this (we use
[Bunnet](https://roman-right.github.io/bunnet/) ODM for MongoDB):
```python
class Product(Document):
    code: Indexed(str, unique=True)   # -> our unique "key"
    product_name: str | None = None   # -> we also create index on this field since it might be useful for find/search.

    last_modified_at_veryfi: datetime | None = None
    file_id: str
    
    # other fields extracted from items are included here
    
    class Config:
        # This makes it possible to extend our Product model with all other fields found in extracted items.
        extra = "allow"    


```

> Side note: I decided to split the processing of the files into these two services for two reasons:
> 1. To make services smaller and easier to maintain. Also, to make it easier to extend and add new features
> in the future.
> 2. To make these different processes independent (reading of the file and inserting into database) so the services
> could be scaled independently according to the needs of the processing pipeline.
>  
> That makes the whole pipeline more robust and easier to scale in the future.

---
The API contains several other endpoints that makes it easier to use the whole system:

- `/upload/status/{file_id}` - endpoint through which you can track the progress of the processing of the uploaded file.
There you can see the status (which tells you if it was processed or was still processing) and the number of 
total/processed/failed items from the file.
- `/product/find/code/{code}` - endpoint to find a product from the database by code.
- `/product/find/name/partial/{product_name}` - endpoint that does the case-insensitive search by the 
product_name field. It returns up to 20 matches.
- `/product/find/name/exact/{product_name}` - returns product(s) with product_name that exactly matches the search term.


## Instructions for running

### 1. Using docker-compose
The easiest way to run the whole pipeline is by using [docker-compose](https://docs.docker.com/compose/). If you have 
Docker Desktop installed you already have docker-compose installed with it.

Clone the repo and position yourself in the root dir of the project (`cd data-pipeline-challenge`).

Now, you only need to run one command:

```shell
docker-compose up -d
```

It will build all the necessary docker images and will run the containers. 

You can now access the services:
- the API by visiting the OpenAPI docs on [http://localhost/docs](http://localhost/docs). 
You can use the API through the OpenAPI docs.
- the RabbitMQ queues on [http://localhost:15672/#/queues](http://localhost:15672/#/queues) (login is guest/guest)
- the MongoDB using connection string `mongodb://localhost:27017`

To shut down the services you can use the command `docker-compose down`.

---

### 2. Running everything manually
For added flexibility you can run all the services manually:

1. Clone the repo and enter the root dir of the project `cd data-pipeline-challenge`.
2. Install MongoDB or run it in a docker container. Create database called `veryfi`.
3. Install RabbitMQ or run it in a docker container. Load definitions by running 
`rabbitmqctl import_definitions docker/rabbitmq_definitions.json`.
4. Install the requirements (you can use the virtualenv here) by running `pip install -r requirements.txt`.
5. Copy the `.env.template` to the `app` dir and rename it to `.env` -> `cp .env.template app/.env`. 
6. Update the variables inside `.env` file with values for local MongoDB and RabbitMQ.
7. Run the API: `uvicorn app.api.main:app --reload --host 0.0.0.0`.
8. Open new terminal window and enter the root dir of the project.
9. Run the FileSplitter service: `python -m app.processing.file_splitter`.
10. Open new terminal window and enter the root dir of the project.
11. Run the DataProcessor service: `python -m app.processing.data_processor`.

The API OpenAPI docs will now be at [http://0.0.0.0:8000/docs](http://0.0.0.0:8000/docs). MongoDB and RabbitMQ will 
depend on the configuration you have set.

---

## Some architectural decisions

### MongoDB
I noticed that the data in the example json file varies a lot and that there aren't many fields
that are in all records. Also, there wasn't the need for some explicit relations between the data records. 
Because of that I decided to use a NoSQL document database, so I can use the flexibility 
of that kind of database. I used MongoDB because I already had some previous experience with it, and it is the most
popular database of that kind.

### Using both MongoDB _id and code in the DB records
I thought about using `code` key directly as an _id field but decided against it. I decided I will keep the MongoDB
_id field to be generated by Mongo and have the `code` be a field with a unique index on it. That way I have the 
strictness and speed of a unique index on code but also flexibility for the future to use the MongoDB _id if necessary.

### RabbitMQ 
I decided to use directly RabbitMQ instead of using Celery (with RabbitMQ or Redis as a broker) for task distribution.
I have a lot of experience with RabbitMQ and didn't see the need to use the Celery on top of it.

## Next steps

### Add tests
Even though I tested the whole pipeline with all kinds of different scenarios, the first next step would be to add some
proper testing. Unit testing but also some end-to-end testing.

### Improve find/search APIs
It would be nice to add some better find/search APIs, so we can better explore the ingested data and make it easier
for AI algorithms to fetch data. Some ideas: pagination, search over multiple record fields, etc.