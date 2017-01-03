from __future__ import division
from bs4 import BeautifulSoup
import nltk, re, pprint
import requests
from nltk.collocations import *
import sys, traceback
from datetime import datetime
import codecs
from multiprocessing import Process, Queue
from urlparse import urlparse
from itertools import groupby
from operator import itemgetter
import itertools
import textwrap

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

def get_scrapable_links(previous_layer_file, remove_duplicate_links, final_file, stats_file):
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
        #also write links to end of stats file
        with codecs.open(stats_file, 'a', encoding="utf-8") as g:
            g.write('LINKS ON PAGE:' + '\n')
            wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150)
            for link in clean_links:
                wrapped = wrapper.fill(link)
                g.write(wrapped  + '\n')
    else:
        print "LOOKS LIKE THERE WEREN'T ANY CONNECTABLE LINKS IN %s" %  previous_layer_file

        
def find_stats(stats):
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
        print "Found sentences with stats in them"
        return stat_sentences
    else:
        print "No sentences with stats found on page"   
     
def pull_data(url, links_file, stats_file):
    '''Pulls all stats from <p> tags of m1 and writes to file, then collects links on page and links from pages that those links 
    point to. It goes n layers deep and then stops.'''
    
    #create a dictionary to hold elements of that will be pulled from page
    page_info = {}
    page_info['SITE'] = url
    
    #create Beautiful Soup object from current search result url
    text = BeautifulSoup(requests.get(url, timeout=7.00).text, "html.parser")
    
    '''First, collect lists and h1 or title tag from page'''
    
    print "STARTING NEW M1: looking for lists at %s" % url
    #pull h1 or title (for html5 pages) tag from page and add to dictionary
    print "Looking for an h1 or title tag on page"
    h1 = text.find_all('h1')
    title_tag = text.find_all('title')
    if h1:
        print "Found an h1"
        h1 = [nltk.clean_html(str(tag)) for tag in h1]       
        unicode_h1 = [tag.decode('utf-8') for tag in h1]
        for tag in unicode_h1:
            page_info['PAGE TITLE'] = tag
    elif title_tag:
        print "Found a title tag" 
        title = [nltk.clean_html(str(tag)) for tag in title_tag]
        unicode_title = [tag.decode('utf-8') for tag in title]
        for tag in unicode_title:
            page_info['PAGE TITLE'] = tag
    else: 
        print "No h1 or title tag on page"
            
    #pull <ul> tags and add to dictionary
    print "Looking for <ul> tags on page"
    def pull_ul(tag):
        return tag.name == 'ul' and tag.li and not tag.attrs and not tag.li.attrs and not tag.a 
    ul_tags = text.find_all(pull_ul)
    #check if any <ul> tags were pulled from page
    if ul_tags:
        print "Found <ul> tags on page"
        #find text immediately preceding any <ul> tag and append to <ul> tag 
        ul_with_context = [str(ul.find_previous()) + str(ul) for ul in ul_tags] #convert to string so we can merge <p> and <ul> tags 
        ul_without_html = [nltk.clean_html(tag) for tag in ul_with_context]
        unicode_uls = [tag.decode('utf-8') for tag in ul_without_html] #convert to unicode to avoid ascii error when writing to file
        page_info['UNORDERED LISTS'] = unicode_uls 
    else: 
        print "No <ul> tags on page"
        
    #pull <ol> tags and add to dictionary
    print "Looking for <ol> tags on page"
    def pull_ol(tag):
        return tag.name == 'ol' and tag.li and not tag.attrs and not tag.li.attrs and not tag.a 
    ol_tags = text.find_all(pull_ol)
    #check if any <ol> tags were pulled from page
    if ol_tags:
        print "Found <ol> tags on page"
        #find text immediately preceding any <ol> tag and append to <ol> tag 
        ol_with_context = [str(ol.find_previous()) + str(ol) for ol in ol_tags] #convert to string so we can merge <p> and <ul> tags 
        ol_without_html = [nltk.clean_html(tag) for tag in ol_with_context]
        unicode_ols = [tag.decode('utf-8') for tag in ol_without_html] #convert to unicode to avoid ascii error when writing to file
        page_info['NUMBERED LISTS'] = unicode_ols
    else: 
        print "No <ol> tags on page"
    '''Now, collect stats found in <p> tags'''
    print "Now pulling stats in body text"
    #pull all <p> tags without attributes from m1, convert to strings and dump into list
    raw_paragraph_tags = [str(tag).lower() for tag in text.find_all(lambda tag: tag.name == 'p' and not tag.attrs)] 
    #strip out any tags that contain words also found in junk terms file--this helps us filter out text that appears in headers, footers and rails
    paragraph_tags = [tag.lower() for tag in raw_paragraph_tags]
    junk_terms = open('junk_terms.txt').readlines()
    junk_terms = [l.strip('\n\r') for l in junk_terms]
    regex = re.compile("|".join(r"\b{}\b".format(term) for term in junk_terms))
    clean_paragraph_tags = list(itertools.ifilterfalse(regex.search, paragraph_tags)) 
    # find any numbered lists on page created with <p> tags and separate them from other <p> tags 
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
        #pull the sentences with stats in them
        stat_sentences = find_stats(unicode_regular_ptags) 
        #now strip html from numbered list <p> tags and convert to unicode 
        numbered_ptags = [nltk.clean_html(string) for string in numbered_ptags] 
        unicode_numbered_ptags = [sentence.decode('utf-8').lower() for sentence in numbered_ptags]
        #add tags to dictionary
        page_info['NUMBERED LIST STATS'] = unicode_numbered_ptags 
        page_info['REGULAR STATS'] =  stat_sentences      
    #if there were no <p> tag numbered lists, then check if there were any <p> tags collected at all and pull stats
    elif paragraph_tags:        
        #isolate individual sentences in body text
        joined_paragraphs = nltk.clean_html(' '.join(clean_paragraph_tags)) #join all <p> tag strings in list to form string and strip out html
        full_sentences = nltk.sent_tokenize(joined_paragraphs) #split into sentences 
        #convert all sentences to unicode so they can be written to files without triggering ascii error
        unicoded_sentences = [sentence.decode('utf-8').lower() for sentence in full_sentences]
        #pull the sentences with stats in them
        stat_sentences = find_stats(unicoded_sentences)
        #add tags to dictionary
        page_info['REGULAR STATS'] = stat_sentences
    else:
        print "WOOPS! looks like no <p> tags on this page so no stats from body text available"
    
    '''Now write all the data from page to file'''
    
    #check if there were any tags or stats at all
    if ul_tags or ol_tags or numbered_ptags or paragraph_tags:
        #write site url and page title to file first 
        with codecs.open(stats_file, 'a', encoding="utf8") as file:
            file.write('SITE:' + '\t' + page_info['SITE'] + '\n\n')
            file.write('PAGE TITLE:' + '\t' + page_info['PAGE TITLE'] + '\n\n')
            #write lists to file
            if ul_tags or ol_tags:
                file.write('LISTS:' + '\n') 
                if ul_tags:
                    wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150)
                    for tag in page_info['UNORDERED LISTS']:
                        wrapped = wrapper.fill(tag)
                        file.write(tag + '\n\n')
                else:
                    pass
                if ol_tags:
                    wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150)
                    for tag in page_info['NUMBERED LISTS']:
                        wrapped = wrapper.fill(tag)
                        file.write(wrapped + '\n\n')
                else:
                    pass
            if numbered_ptags or paragraph_tags:
                file.write('STATS:' + '\n')
                if numbered_ptags:
                    first_wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150) #for numbered <p> tags
                    second_wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150) #for regular <p> tags
                    for tag in page_info['NUMBERED LIST STATS']:
                        wrapped = first_wrapper.fill(tag)
                        file.write(wrapped + '\n\n')
                    for tag in page_info['REGULAR STATS']:
                        wrapped = second_wrapper.fill(tag)
                        file.write(wrapped + '\n\n')
                else:
                    pass
                if paragraph_tags:
                    wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150)
                    for tag in page_info['REGULAR STATS']:
                        wrapped = wrapper.fill(tag)
                        file.write(wrapped + '\n\n')
                else:  
                    pass
            else:
                pass
    else: 
        pass
        
    '''Now start collecting links on page'''
    
    print "I'm going to start collecting links on page"
    collected_links = [] #empty list to store links collected from page
    pdf_links = [] #empty list to store links for pdfs
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
                #collect all links for pdfs and dump in list
                if re.search('.pdf$', link.get('href')):
                    pdf_links.append(link.get('href'))
                #collect links that are truncated, i.e something like '/university/small-business/' and append them to base url to generate full link
                if re.search('^/.+', link.get('href')):
                    truncated_collected_links.append(link.get('href'))
            else: 
                pass
    #join truncated links, if any, to base url and add to list with all links
    if truncated_collected_links:
        for link in truncated_collected_links:
            collected_links.append(base_url + link)    
    else:
        pass
        
    #check to see if there were any links collected on m1 
    if collected_links or pdf_links:
        print "Found links on page %s" % url
        remove_duplicate_links = set(collected_links) #remove any duplicate links
        remove_duplicate_pdflinks = set(pdf_links) #remove any duplicate pdf links
        #keep only the regular links that can be scraped
        get_scrapable_links(url, remove_duplicate_links, links_file, stats_file) #test links for connectability and write connectable ones to file
        #write the pdf links to bottom of stats doc
        if pdf_links:
            with codecs.open(stats_file, 'a', encoding="utf8") as file:
                file.write('LINKS TO PDFs:' + '\n')
                wrapper = textwrap.TextWrapper(initial_indent='\t', subsequent_indent='\t', width = 150)
                for link in pdf_links:
                    wrapped = wrapper.fill(link)
                    file.write(wrapped)
            
    else:
        print "No links found on page"      
            
      
def analyze_m1s(url, links_file, stats_file):
    '''Checks if m1 links are active and allow screen scraping before continuing on to screen scraping process'''
 
    try:
        #check if url returns a 200 response
        if requests.get(url, timeout=7.00).status_code == 200:
            try:
                #check 'server' header of m1 to see if screen scraping disallowed
                if not requests.get(url).headers['server'] == 'cloudflare-nginx':
                    pull_data(url, links_file, stats_file) 
                else:
                    print "SCREENSCRAPING PROHIBITED AT %s " % url
            #exception that still pulls links when response header provides no server information, but link is still functional
            except:
                pull_data(url, links_file, stats_file) 
                                   
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
    analyze_m1s('http://contentmarketinginstitute.com/2015/09/b2b-content-marketing-research/', 'SR_LINKS.txt', 'SR_STATS.txt')
            
if __name__ == "__main__":
    print_stats()