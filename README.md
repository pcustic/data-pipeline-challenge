# Veryfi Challenge - Data

This is my submission for a Veryfi data interview challenge. 

In short, the task was following:

> Suppose that Veryfi is building a database of products that may appear on customer receipt
scans. There is no official database of products; Veryfi has to build it from various data sources.
> 
> The dataset includes a sample of 50,000 products in .json format from a website called
openfoodfacts.com, which crowd-sources its information and is publicly available.
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