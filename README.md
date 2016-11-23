The recursive screenscraper (recursive.py) does three things:
1) pulls all statistical information in the body of a webpage
2) pulls all lists in the body of a webpage
3) pulls links in the body of a webpage

Once it has pulled relevant links on the page, it performs the same three operations on those links ad inifinatum. The single page scraper (singlepage.py) performs the same operations on a single page and then stops. 

I use the BeautifulSoup library to parse html and python's Natural Language Toolkit (NLTK) to parse raw text.The program automatically filters out all non-functional links. 
