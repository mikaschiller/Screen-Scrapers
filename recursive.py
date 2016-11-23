from __future__ import division
from bs4 import BeautifulSoup
import nltk, re, pprint
import requests
import collections
from nltk.collocations import *
import sys, traceback
from datetime import datetime
import os
import os.path
import codecs
from multiprocessing import Process, Queue
from urlparse import urlparse
from itertools import groupby
from operator import itemgetter
import itertools

def check_url_scrapability(dirty_queu, clean_queue):
    '''Checks whether links allow screenscraping for the get_scrapable_links() function and it does multiprocessing by 
    having 4 cores check if a link returns a 200 HTTP response'''
    
    for link in iter(dirty_queu.get, 'STOP'):
        try:
            if requests.get(link, timeout=7.00).status_code == 200 or 201 or 202 or 203 or 206 or 207 or 208 or 226:
                try:
                    if not requests.get(link).headers['server'] == 'cloudflare-nginx':
                        clean_queue.put(link)
                    else:
                        print "SCREENSCRAPING PROHIBITED AT %s " % link   
                except:
                    clean_queue.put(link)
                    pass                     
            else:
                print "UNABLE TO GET A 200 LEVEL HTTP RESPONSE AT %s " % link
        except requests.exceptions.Timeout as e:
            #client couldn't connect to server or return data in time period specified in timeout parameter in requests.get()
            print e.message
            pass  
        except requests.exceptions.ConnectionError as e:
            #in case of faulty url
            print e.message
            pass           
        except Exception, err:
            #catch regular errors
            print(traceback.format_exc())            
        except requests.exceptions.HTTPError as e:
            print e.message
            pass
        except requests.exceptions.TooManyRedirects as e:
            print e.message
            pass
    return True

def get_scrapable_links(previous_layer_file, remove_duplicate_links, final_file):
    '''Filters out links that either don't permit screen scraping or aren't connectable for some reason. We use all the 
    machine's cores to speed up processing'''
    
    clean_links = []
    workers = 4 #the number of cores we will be utilizing
    processes = [] #empty list to place each core process that will be checking link connectability
    dirty_queu = Queue() #place links for all cores to check connectability 
    clean_queue = Queue() #place connectable links here after all cores have checked their connectability
    
    #loop through links collected on a page and dump them in a queu so that all processes can pull links from it
    for url in remove_duplicate_links:
        dirty_queu.put(url)
    #make all cores check connectability of links in queu
    if previous_layer_file[:4] == 'http':
        print 'There were %d links collected from %s' %(len(remove_duplicate_links), previous_layer_file)
    else:
        print 'There were %d links collected from links in %s ' %(len(remove_duplicate_links), previous_layer_file)  
    print 'Checking to see how many of those links are connectable'
    startTime = datetime.now() #start timer to time how long it takes to check link connectability 
    for w in xrange(workers):
        p = Process(target = check_url_scrapability, args = (dirty_queu, clean_queue)) #check_url_scrapability function checks links for 200 status using 4 cores
        p.start()
        processes.append(p)
        dirty_queu.put('STOP')
    for p in processes:
        p.join()
    clean_queue.put('STOP')
    print 'Time it took to check connectability of links is:', (datetime.now() - startTime)
    
    #place all link that returned a HTTP 200 status to empty list
    for link in iter(clean_queue.get, 'STOP'):
        clean_links.append(link)       
    
    #check to see if there were any connectable links at all and write them to file, else don't continue
    if clean_links:
        print 'Writing %d connectable links to file %s ' % (len(clean_links), final_file)
        with codecs.open(final_file, 'w', encoding="utf-8") as g:
            for link in clean_links:
                g.write(link + '\n') #write scrapable links to final file
    else:
        print "LOOKS LIKE THERE WEREN'T ANY CONNECTABLE LINKS IN %s" %  previous_layer_file
    
    
def pull_andwrite_lists(lists_file, webpage):
    '''This function pulls all ordered and unordered lists in body text of a webpage and writes them to a file. We use beautiful soup
     functions below to do the extraction due to its complexity. We pull only <ul> and <ol> that don't have attributes and who's <li>
    don't have attributes or <a> tags because ones that have those qualities  are generally junk that appear in the rails or headers/footers 
    of a web page'''
    
    #pull <ul> tags
    def pull_ul(tag):
        return tag.name == 'ul' and tag.li and not tag.attrs and not tag.li.attrs and not tag.a 
    ul_tags = webpage.find_all(pull_ul)
    #find the <p> tag immediately preceding any <ul> tag and merge them
    ul_with_context = [str(ul.find_previous("p")) + str(ul) for ul in ul_tags] #convert to string so we can merge <p> and <ul> tags 
    unicode_uls = [sentence.decode('utf-8') for sentence in ul_with_context] #convert to unicode to avoid ascii error when writing to file
    
    #pull all <ol> tags
    def pull_ol(tag):
        return tag.name == 'ol' and tag.li and not tag.attrs and not tag.li.attrs and not tag.a
    ol_tags = webpage.find_all(pull_ol)
    #find the <p> tag immediately preceding any <ol> tag and merge them
    ol_with_context = [str(ul.find_previous("p")) + str(ul) for ul in ol_tags] #convert to string so we can merge <p> and <ul> tags
    unicode_ols = [sentence.decode('utf-8') for sentence in ol_with_context] #convert to unicode to avoid ascii error when writing to file
    
    #write <ul> and <ol> tags to file
    if ul_tags:
        print "Found bulleted list(s) on page and writing to file %s" % lists_file
        with codecs.open(lists_file, 'a', encoding="utf8") as file:
            for tag in unicode_uls:
                file.write(nltk.clean_html(tag) + '\n\n')
    else:
        print "No bulleted list(s) found on page"
        pass
    if ol_tags:
        print "Found ordered list(s) on page and writing to file %s" % lists_file
        with codecs.open(lists_file, 'a', encoding="utf8") as file:
            for tag in unicode_ols:
                file.write(nltk.clean_html(tag) + '\n\n')
    else:
        print "No ordered list(s) found on page"
        pass

def write_stats_to_file(stats, stats_file):
    '''A function that writes stats collected from pages to file. It collects the sentence before and the sentence after the stat to 
    lend context to the sentence that contains the stat.'''
    
    indexes = [] #container to store sentences with stats in them
    #find the indexes of sentences with stats in them
    for index, sentence in enumerate(stats):
        if (re.findall('\d+', sentence) or re.findall('''\\btwo\\b|\\bthree\\b|\\bfour\\b|\\bfive\\b|\\bsix\\b|\\bseven\\b|\\beight\\b|\\bnine\\b|\\bten\\b| 
            #\\beleven\\b|\\btwelve\\b|\\bthirteen\\b|\\bfourteen\\b|\\bfifteen\\b|\\bsixteen\\b|\\bseventeen\\b|\\beighteen\\b|\\bnineteen\\b|\\btwenty\\b|\\bthirty\\b
            #|\\bforty\\b|\\bfifty\\b|\\bsixty\\b|\\bseventy\\b|\\beighty\\b|\\bninety\\b|\\bhundred\\b|\\bthousand\\b|
                #\\bmillion\\b|\\bbillion\\b|\\btrillion\\b|%|\\bpercent\\b''', sentence)):
                    indexes.append(index)
    #group together the indexes of sequences of sentences with stats in them 
    index_groupings = [map(itemgetter(1), g) for k, g in groupby(enumerate(indexes), lambda (i, x): i-x)]
    
    #pull the final index in list of tokenized sentences to use in find_beforeafter_indexes() function below
    last_index = len(stats) -1
    
    #pull sentence before and sentence after sequence with numbers in it
    def find_beforeafter_indexes(index_groupings):
        '''This function looks at all index groupings above and pulls the index directly before the first index in the grouping and 
        the index directly after the last index in the grouping. So if an index grouping is [2,3], it would return [1,2,3,4]. These are
        then used to pull sentences from tokenized text. All this is done to ensure that we always pull the sentence before and the sentence 
        after and sentence sequence with numbers in it. If any indexes in the groupings are beginning ([0]) or ending indexes ([-1]), it 
        doesn't pull preceding and subsequent index.'''
    
        if index_groupings[position][0] != 0:
            new_firstindex = index_groupings[position][0] -1 
            index_groupings[position].insert(0, new_firstindex)
        else:
            pass
        if index_groupings[position][-1] != last_index:
            new_finalindex = index_groupings[position][-1] +1
            index_groupings[position].append(new_finalindex)
        else:
            pass       
    for position in range(len(index_groupings)):
        if len(index_groupings[position]) > 1:
            find_beforeafter_indexes(index_groupings)
        else:
            find_beforeafter_indexes(index_groupings)
        
    stat_sentences = [" ".join(map(lambda x:stats[x],i)) for i in index_groupings]
    #map the indexes to the sentences with stats in them
    stat_sentences = [" ".join(map(lambda x:stats[x],i)) for i in index_groupings]
    
    #check if there were any stats collected on page and write to file 
    if stat_sentences: 
        print "Found stats and writing them to file %s" % stats_file                
        with codecs.open(stats_file, 'a', encoding="utf8") as file:
            for sentence in stat_sentences:
                file.write(sentence + '\n\n')
    else:
        print "No stats available"
        
def pull_stats_lists(raw_paragraph_tags, stats_file, lists_file, webpage):
    '''A function that pulls stats and lists and writes them to files. It uses the functions pull_andwrite_lists() and
    write_stats_to_file() to accomplish that.'''
    
    '''First, pull stats and write to file'''
    
    #strip out any tags that contain words also found in junk terms file--this helps us filter out text that appears in headers, footers and rails
    paragraph_tags = [tag.lower() for tag in raw_paragraph_tags]
    junk_terms = open('junk_terms.txt').readlines()
    junk_terms = [l.strip('\n\r') for l in junk_terms]
    regex = re.compile("|".join(r"\b{}\b".format(term) for term in junk_terms))
    clean_paragraph_tags = list(itertools.ifilterfalse(regex.search, paragraph_tags)) 
    # find any numbered lists on page created with <p> tags and separate them from other <p> tags 
    print "Pulling data from NEW LINK"
    numbered_ptags = [] #empty list to store <p> tags used to create numbered list 
    for position in range(len(clean_paragraph_tags)):
        if re.search(r'^<p>1\.', clean_paragraph_tags[position]): #collect the sentence before <p>1. to lend context to list
            numbered_ptags.append(clean_paragraph_tags[position -1])
        if re.search(r'^<p>\d+', clean_paragraph_tags[position]):
            numbered_ptags.append(clean_paragraph_tags[position])       
    #check if there were any numbered lists created with <p> tags and if so, proceed with separating them from regular <p> tags
    if numbered_ptags:
        print "Detected numbered list that uses <p> tags on page"
        #find all <p> tags that aren't used to created numbered list 
        regular_ptags = [tag for tag in clean_paragraph_tags if tag not in numbered_ptags]
        #isolate individual sentences from regular <p> tags
        joined_paragraphs = nltk.clean_html(' '.join(regular_ptags)) #join all <p> tag strings in list to form string and strip out html
        full_sentences = nltk.sent_tokenize(joined_paragraphs) #split into sentences
        #convert all sentences to unicode so they can be written to files without triggering ascii error 
        unicode_regular_ptags = [sentence.decode('utf-8').lower() for sentence in full_sentences] 
        #now strip html from numbered list <p> tags and convert to unicode 
        numbered_ptags = [nltk.clean_html(string) for string in numbered_ptags] 
        unicode_numbered_ptags = [sentence.decode('utf-8').lower() for sentence in numbered_ptags] 
        #write all stats to files
        #first write numbered list <p> tag sentences in m1 to file; we're not going to use write_stats_to_file() function because these stats need to be configured a bit differently than regular stats 
        print "Writing this list to file %s" % lists_file
        with codecs.open(lists_file, 'a', encoding="utf8") as file:
            for string in unicode_numbered_ptags:
                file.write(string + '\n')
        #write regular stats to file
        write_stats_to_file(unicode_regular_ptags, stats_file)                       
    #if there were no <p> tag numbered lists, then check if there were any <p> tags collected at all and pull stats
    elif paragraph_tags:        
        #isolate individual sentences in body text
        joined_paragraphs = nltk.clean_html(' '.join(clean_paragraph_tags)) #join all <p> tag strings in list to form string and strip out html
        full_sentences = nltk.sent_tokenize(joined_paragraphs) #split into sentences 
        #convert all sentences to unicode so they can be written to files without triggering ascii error
        unicoded_sentences = [sentence.decode('utf-8').lower() for sentence in full_sentences] 
        #write stats to file, if any  
        write_stats_to_file(unicoded_sentences, stats_file)
    else:
        print "WOOPS! looks like no <p> tags on this page so no stats from body text available" 
    
    '''Now pull bulleted and numbered lists and write to file'''
     
    print "Now checking if there are any bulleted or ordered lists on page"
    pull_andwrite_lists(lists_file, webpage)
        
def collect_links(url, previous_layer_file, final_file):
    ''' A helper function that loops through a list with links and extracts links on each page that those links point to. It's used by pull_tags() function
    to extract several layers of links on a search result so that we can pull stats and lists on those pages. It removes junk links 
    and also links that don't allow screen scraping or a server connection by using the get_scrapable_links() function.'''

    links = [] #store links collected from articles linked to in previous layer 
    web_connection = [] #store web connection objects for every url that comes from previous layer
    
    #collect links in previous layer of links and add to empty list
    #first check if there were any links at all collected from previous layer by checking if there was a file even created    
    if os.path.isfile(previous_layer_file):
        print 'Retreiving links from file %s and creating Beautiful Soup objects to extract links from those links' % previous_layer_file
        text_file = codecs.open(previous_layer_file, 'r', encoding="utf-8")
        for line in text_file:
            for link in line.split():
                links.append(link)
        text_file.close()
        #get links from pages that links from previous layer point to and write to file        
        startTime = datetime.now() #start timer to time how long it takes to create beautiful soup objects
        for link in links:
            try:
                web_connection.append(BeautifulSoup(requests.get(link, timeout=7.00).text), "html.parser")
            except requests.exceptions.Timeout as e:
                #client couldn't connect to server or return data in time period specified in timeout parameter in requests.get()
                print e.message 
                pass 
            except requests.exceptions.ConnectionError as e:
                #in case of faulty url
                print e.message 
                pass          
            except Exception, err:
                #catch regular errors
                print(traceback.format_exc())
                pass
            except requests.exceptions.HTTPError as e:
                print e.message
                pass
            except requests.exceptions.TooManyRedirects as e:
                print e.message
                pass 
        print 'The time it took to create Beautiful Soup objects is :', (datetime.now() - startTime)
        if web_connection:  #verify that at least one Beautiful Soup object was created
            #start collecting links from pages previous layer links point to
            startTime2 = datetime.now() #start timer to time link collection
            print 'Looking for links within links in file %s ' % previous_layer_file
            raw_paragraph_tags = [] #empty list to store <p> tags without attributes
            #extract <p> tags and convert to beautiful soup objects so we can pull links
            for beaut_soup_object in web_connection:
                for tag in beaut_soup_object.find_all(lambda tag: tag.name == 'p' and not tag.attrs):
                    raw_paragraph_tags.append(str(tag).lower())
            #strip out any tags that contain words also found in junk terms file
            collected_links = [] #empty list to store links collected from pages
            junk_terms = open('junk_terms.txt').readlines()
            junk_terms = [l.strip('\n\r') for l in junk_terms]
            regex = re.compile("|".join(r"\b{}\b".format(term) for term in junk_terms))
            clean_paragraph_tags = list(itertools.ifilterfalse(regex.search, raw_paragraph_tags)) 
            soup_tags = [BeautifulSoup(tag, "html.parser") for tag in clean_paragraph_tags] #convert <p> tags to soup objects so we can pull links from them
            #extract the links from the <p> tag beautiful soup objects
            for beautiful_soup_object in soup_tags:
                for link_tag in beautiful_soup_object.find_all('a'):
                    if link_tag.get('href') is not None: #filter out any links which are empty objects
                        if re.search('^https?://.+', link_tag.get('href')) and not re.search(' ', link_tag.get('href')) and not re.search('.png$', link_tag.get('href')) and not re.search('.jpg$', link_tag.get('href')) and not re.search('.pdf$', link_tag.get('href')): #filter out junk links
                            collected_links.append(link_tag.get('href'))
                        else:
                            pass
                    else:
                        pass
            #check to see if there were any links collected 
            if collected_links:     
                print 'The time it took to collect links from the links is:', (datetime.now() - startTime2)
                remove_duplicate_links = list(set(collected_links)) #remove duplicate links using set() function and convert object back to list so we can do index slicing
                #keep number of links to no more than 350 to speed up performance
                if len(remove_duplicate_links) > 200:
                    remove_duplicate_links = collected_links[:200]
                get_scrapable_links(previous_layer_file,remove_duplicate_links, final_file)
                               
            else:
                print "I couldn't find any. This ends link collection process for %s" % url    
        else:
            pass                   
    else:
        pass
        
def pull_data(url, final_file1, final_file2, final_file3, final_file4, final_file5, stats_file, lists_file):
    '''Pulls all stats from <p> tags without attributes of m1 and writes to file, then collects links on page and links from pages that those links 
    point to. It goes n layers deep and then stops.'''
    
    #create Beautiful Soup object from current search result url
    text = BeautifulSoup(requests.get(url, timeout=7.00).text, "html.parser")
    
    #pull all <p> tags without attributes from m1, convert to strings and dump into list
    print "STARTING NEW M1: looking for <p> tags at %s" % url
    print "Now checking for stats and lists on page"
    raw_paragraph_tags = [str(tag).lower() for tag in text.find_all(lambda tag: tag.name == 'p' and not tag.attrs)]   
 
    '''First, we start collecting stats and lists on page m1 and write to file'''
    pull_stats_lists(raw_paragraph_tags, stats_file, lists_file, text)
    
    '''Now we start collecting links on m1'''
        
    print "I'm going to start collecting links on m1 now"
    print 'Will search for links on page %s and create Beautiful Soup objects to extract links from those links' % url
    collected_links = [] #empty list to store links collected from page
    truncated_collected_links = [] #empty container to store any truncated page urls i.e '/1576-marketing-your-product.html' collected on page
    # define a variable that holds base url of page i.e 'http://www.businessnewsdaily.com' so that we can combine it with any truncated page urls i.e '/1576-marketing-your-product.html' if need be
    page_url = urlparse(url)
    base_url = '{url.scheme}://{url.netloc}/'.format(url = page_url)
    base_url = base_url[:-1]
    #convert paragraph tags into soup objects so that we can pull <a> tags from them
    #strip out any tags that contain words also found in junk terms file--this helps us strip out links that appear in header, footer and rails
    junk_terms = open('junk_terms.txt').readlines()
    junk_terms = [l.strip('\n\r') for l in junk_terms]
    regex = re.compile("|".join(r"\b{}\b".format(term) for term in junk_terms))
    clean_paragraph_tags = list(itertools.ifilterfalse(regex.search, raw_paragraph_tags))  
    soup_tags = [BeautifulSoup(tag, "html.parser") for tag in clean_paragraph_tags] #convert <p> tags to soup objects so we can pull links from them
    for tag in soup_tags:
        for link in tag.find_all('a'):  
            if link.get('href') is not None: #filter out any objects that aren't strings
                if re.search('^https?://.+', link.get('href')) and not re.search('.png$', link.get('href')) and not re.search(' ', link.get('href')) and not re.search('.jpg$', link.get('href')) and not re.search('.pdf$', link.get('href')):  #filter out junk links
                    collected_links.append(link.get('href'))
                #collect links that are truncated, i.e something like '/university/small-business/' and append them to base url to generate full link
                if re.search('^/.+', link.get('href')):
                    truncated_collected_links.append(link.get('href'))
    #join truncated links, if any, to base url and add to list with all links
    if truncated_collected_links:
        for link in truncated_collected_links:
            collected_links.append(base_url + link)    
    else:
        pass
        
    #check to see if there were any links collected on m1 
    if collected_links:
        print "Found links on m1 page %s" % url
        remove_duplicate_links = set(collected_links) #remove any duplicate links
        get_scrapable_links(url, remove_duplicate_links, final_file1) #test links for connectability and write connectable ones to file
        
        '''Here we start collecting links within links within links so that we can get stats and lists from articles that are several
        links deep away from the article on page 1 of search result. We go several layers down from main article.'''
        
        print "Done pulling links from m1 page %s" % url
        print "I'm now going to start collecting links from those links and go several layers down"

    
        #collect links two clicks down from search result in LAYER 2 and write to file 
        collect_links(url, final_file1, final_file2)
        #collect links three clicks down from search result in LAYER 3 and write to file
        collect_links(url, final_file2, final_file3)
        #collect links four clicks down  from search result in LAYER 4 and write to file
        #collect_links(url, final_file3, final_file4)
        #collect links five clicks down from search result in LAYER 5 and write to file
        #collect_links(url, final_file4, final_file5) 
        print "Finished link collection process"
        '''Now we start collecting stats and lists in all links collected for current search result and write them to files'''
        
        print "Now will try to collect stats and lists for links in all SCRAPABLE.txt files for search result"
        #open each file with scrapable links for current search result and dump its links into list
        #for example, if current search is SR1, only open files that start with 'SR1'      
        search_result_files = [] #empty list to store file names for current search result
        for file in os.listdir("/Users/mikaschiller/Desktop/Python_Practice_Code/Learn_Python_the_Hard_Way/projects/skeleton/djangosites/engine/automated/"):
            #final_file3 is an arbitrary choice below...chose it only because we had to pick at least one file with links for current search result
            if file.startswith(final_file3[:4]):
                search_result_files.append(file)
        if search_result_files: #check to make sure there were any files at all created for current search result
            #pull stats and lists and write to files
            pull_nonm1_statslists(search_result_files, stats_file, lists_file)            
        else:
            print "WOOPS! Looks like no files with valid links found for this search result. Ending analysis"
    else:
        print "WOOPS! I couldn't find any links at %s, so this ends analysis" % url      

def pull_nonm1_statslists(search_result_files, stats_file, lists_file):
    '''Pulls stats and lists from links that were collected in all layers of the current search result and writes 
    them to files'''   
    
    startTime = datetime.now()
    for file in search_result_files: 
        links = [] #empty list to store links from file
        text_file = codecs.open(file, 'r', encoding="utf-8") 
        for line in text_file: 
            for link in line.split(): 
                links.append(link) 
        text_file.close()
    
        '''loop through all links collected in the current layer'''
        
        raw_html = [] #store html object for each link from file 
        #retrieve the page html for each link
        for link in links:
            try: 
                raw_html.append(BeautifulSoup(requests.get(link, timeout=7.00).text, "html.parser"))
            except requests.exceptions.Timeout as e:
                #client couldn't connect to server or return data in time period specified in timeout parameter in requests.get()
                print e.message 
                pass 
            except requests.exceptions.ConnectionError as e:
                #in case of faulty url
                print e.message  
                pass         
            except Exception, err:
                #catch regular errors
                print(traceback.format_exc())
                pass
            except requests.exceptions.HTTPError as e:
                print e.message
                pass
            except requests.exceptions.TooManyRedirects as e:
                print e.message
                pass  
        #collect all stats and links from all non-m1 links  
        for position in range(len(raw_html)):
            raw_paragraph_tags = [str(tag) for tag in raw_html[position].find_all(lambda tag: tag.name == 'p' and not tag.attrs)]
            pull_stats_lists(raw_paragraph_tags, stats_file, lists_file, raw_html[position])
    
    
def analyze_m1s(url, final_file1, final_file2, final_file3, final_file4, final_file5, stats_file, lists_file):
    '''Checks if m1 links are active and allow screen scraping before continuing on to screen scraping process'''
 
    try:
        #check if url returns a 200 response
        if requests.get(url, timeout=7.00).status_code == 200:
            try:
                #check 'server' header of m1 to see if screen scraping disallowed
                if not requests.get(url).headers['server'] == 'cloudflare-nginx':
                    pull_data(url, final_file1, final_file2, final_file3, final_file4, final_file5, stats_file, lists_file) 
                else:
                    print "SCREENSCRAPING PROHIBITED AT %s " % url
            #exception that still pulls links when response header provides no server information, but link is still functional
            except:
                pull_data(url, final_file1, final_file2, final_file3, final_file4, final_file5, stats_file, lists_file) 
                                   
        else:
            print "UNABLE TO GET A 200 HTTP RESPONSE AT %s " % url   
                                   
    except requests.exceptions.Timeout as e:
        #client couldn't connect to server or return data in time period specified in timeout parameter in requests.get()
        print e.message 
        pass
    except requests.exceptions.ConnectionError as e:
        #in case of faulty url
        print e.message
        pass           
    except Exception, err:
        #catch regular errors
        print(traceback.format_exc())
        pass
    except requests.exceptions.HTTPError as e:
        print e.message
        pass
    except requests.exceptions.TooManyRedirects as e:
        print e.message
        pass            
def print_stats():
    '''Writes to file all language with statistics in it and any ordered lists in all search results and their embedded links.'''  
           
    #collect links from all search results
    analyze_m1s('https://newrepublic.com/article/134163/barack-obama-mr-clean-perfect-surrogate-hillary-clinton', 'SR1L1_SCRAPABLE.txt', 'SR1L2_SCRAPABLE.txt', 'SR1L3_SCRAPABLE.txt', 'SR1L4_SCRAPABLE.txt', 'SR1L5_SCRAPABLE.txt', 'SR1_STATS.txt', 'SR1_LISTS.txt')
    #analyze_m1s('http://contentmarketinginstitute.com/what-is-content-marketing/', 'SR2L1_SCRAPABLE.txt', 'SR2L2_SCRAPABLE.txt', 'SR2L3_SCRAPABLE.txt', 'SR2L4_SCRAPABLE.txt', 'SR2L5_SCRAPABLE.txt','SR2_STATS.txt', 'SR2_LISTS.txt')
    #analyze_m1s('https://www.ama.org/publications/MarketingNews/Pages/what-lies-ahead.aspx', 'SR3L1_SCRAPABLE.txt', 'SR3L2_SCRAPABLE.txt', 'SR3L3_SCRAPABLE.txt', 'SR3L4_SCRAPABLE.txt', 'SR3L5_SCRAPABLE.txt', 'SR3_STATS.txt', 'SR3_LISTS.txt')
    #analyze_m1s('https://www.linkedin.com/pulse/business-growth-content-marketing-biggest-pain-points-serge-trad', 'SR4L1_SCRAPABLE.txt', 'SR4L2_SCRAPABLE.txt', 'SR4L3_SCRAPABLE.txt', 'SR4L4_SCRAPABLE.txt', 'SR4L5_SCRAPABLE.txt', 'SR4_STATS.txt', 'SR4_LISTS.txt')
    #analyze_m1s('http://copytactics.com/customers-pain-points', 'SR5L1_SCRAPABLE.txt', 'SR5L2_SCRAPABLE.txt', 'SR5L3_SCRAPABLE.txt', 'SR5L4_SCRAPABLE.txt', 'SR5L5_SCRAPABLE.txt', 'SR5_STATS.txt', 'SR5_LISTS.txt')
    #analyze_m1s('https://marketinginsidergroup.com/content-marketing/the-four-biggest-content-marketing-pain-points/', 'SR6L1_SCRAPABLE.txt', 'SR6L2_SCRAPABLE.txt', 'SR6L3_SCRAPABLE.txt', 'SR6L4_SCRAPABLE.txt', 'SR6L5_SCRAPABLE.txt', 'SR6_STATS.txt', 'SR6_LISTS.txt')
    #analyze_m1s('https://forbesnonprofitcouncil.com/blog/2016/02/22/4-ways-to-conquer-your-content-marketing-pain-points/', 'SR7L1_SCRAPABLE.txt', 'SR7L2_SCRAPABLE.txt', 'SR7L3_SCRAPABLE.txt', 'SR7L4_SCRAPABLE.txt', 'SR7L5_SCRAPABLE.txt', 'SR7_STATS.txt', 'SR7_LISTS.txt')
    #analyze_m1s('http://www.madmarketer.com/topics/tips-and-tricks/articles/415660-content-marketing-remains-top-pa-point-companies.htm', 'SR8L1_SCRAPABLE.txt', 'SR8L2_SCRAPABLE.txt', 'SR8L3_SCRAPABLE.txt', 'SR8L4_SCRAPABLE.txt', 'SR8L5_SCRAPABLE.txt', 'SR8_STATS.txt', 'SR8_LISTS.txt') 
    #analyze_m1s('https://medium.com/@daisyqin/5-b2b-content-marketing-pain-points-2bee1430be5#.4qwjoj2dy', 'SR9L1_SCRAPABLE.txt', 'SR9L2_SCRAPABLE.txt', 'SR9L3_SCRAPABLE.txt', 'SR9L4_SCRAPABLE.txt', 'SR9L5_SCRAPABLE.txt', 'SR9_STATS.txt', 'SR9_LISTS.txt')  
    #analyze_m1s('https://www.techvalidate.com/blog/the-content-marketing-conundrum-831', 'SR10L1_SCRAPABLE.txt', 'SR10L2_SCRAPABLE.txt', 'SR10L3_SCRAPABLE.txt', 'SR10L4_SCRAPABLE.txt', 'SR10L5_SCRAPABLE.txt', 'SR10_STATS.txt', 'SR10_LISTS.txt') 
        
if __name__ == "__main__":
    print_stats()