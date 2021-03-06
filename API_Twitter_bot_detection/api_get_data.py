import requests
import pandas as pd
from API_Twitter_bot_detection.utils import count_mentions, encoding_reply, tokenize, remove_stopwords, lemmatize,embed_sentence
from nltk.tokenize import TweetTokenizer
from tensorflow.keras.preprocessing.sequence import pad_sequences
import numpy as np



def user_data_request(username):
    headers = {
        'Authorization':
        'Bearer AAAAAAAAAAAAAAAAAAAAAGRNVwEAAAAA0khTD6u%2B1DoYpB%2BM%2B9OVcUNl5Pc%3DaKJmBoEn1exhbwQkVygK0hYysIU6kiCn1qGqymbHzgTeEzHqzD'
    }
    try:
        response = requests.get(
            f'https://api.twitter.com/2/users/by/username/{username}?user.fields=id,name,username,created_at,description,profile_image_url,location,verified,protected,public_metrics',
            headers=headers).json()
        user = pd.DataFrame(pd.Series(response['data'])).T
        u_org = user[['id', 'username', 'name', 'description', 'created_at', 'verified','protected','public_metrics']]
        u_org['followers_count'] = [i['followers_count'] for i in u_org['public_metrics']]

        u_org['following_count'] = [i['following_count'] for i in u_org['public_metrics']]

        u_org['tweet_count'] = [i['tweet_count'] for i in u_org['public_metrics']]

        u_org['listed_count'] = [i['listed_count'] for i in u_org['public_metrics']]

        user_processed = u_org[[
            'id', 'username', 'name', 'description', 'created_at',
            'verified', 'protected', 'followers_count',
            'following_count', 'tweet_count', 'listed_count'
        ]]
        return user_processed
    except:
        df = pd.DataFrame(columns={'empty': 0})

        return df


def tweet_data_request(user_processed):
    headers = {
        'Authorization':
        'Bearer AAAAAAAAAAAAAAAAAAAAAGRNVwEAAAAA0khTD6u%2B1DoYpB%2BM%2B9OVcUNl5Pc%3DaKJmBoEn1exhbwQkVygK0hYysIU6kiCn1qGqymbHzgTeEzHqzD'
    }
    user = user_processed['id'][0]
    try:
        url = f'https://api.twitter.com/2/users/{user}/tweets?exclude=retweets&expansions=attachments.media_keys,author_id,entities.mentions.username,in_reply_to_user_id,referenced_tweets.id&tweet.fields=attachments,created_at,in_reply_to_user_id,lang,possibly_sensitive,public_metrics,referenced_tweets,text&max_results=100'
        response = requests.get(url, headers=headers).json()['data']
        template = pd.read_parquet('API_Twitter_bot_detection/data/template_twdf.parquet')
        df = template.append(response)
        df = df[df['author_id'] == user]

        ### time processing

        df = df.sort_values(by=['author_id', 'created_at'],
                            ascending=True,
                            ignore_index=True)

        df['created_at'] = pd.to_datetime(df['created_at'])

        df['lag'] = df.groupby('author_id', as_index=False)['created_at'].diff(
        )  ### this line creates the lag column - difference of time between tweets made by user

        ##contain attachments?

        df['attachments'] = df['attachments'] == df['attachments']

        ##public metrics unpacking

        df['like_count'] = [i['like_count'] for i in df['public_metrics']]

        df['quote_count'] = [i['quote_count'] for i in df['public_metrics']]

        df['reply_count'] = [i['reply_count'] for i in df['public_metrics']]

        df['retweet_count'] = [
            i['retweet_count'] for i in df['public_metrics']
        ]

        ###entities unpacking

        df['n_mentions'] = df['entities'].apply(count_mentions)

        ##reply category

        df['reply_category'] = df.apply(lambda row: encoding_reply(row),
                                        axis=1)

        ##contain references?

        df['referenced_tweets'] = df['referenced_tweets'] == df[
            'referenced_tweets']

        ##converting author id to integer

        df['author_id'] = df['author_id'].astype(int)

        ##organizing df

        df = df[[
            'author_id', 'id', 'lang', 'text', 'created_at', 'lag',
            'possibly_sensitive', 'referenced_tweets', 'reply_category',
            'like_count', 'quote_count', 'reply_count', 'retweet_count',
            'n_mentions'
        ]]

    except Exception as e:
        print(f'Could not fetch tweets from user.{str(e)}')
        df = pd.DataFrame(columns={'empty': 0})

    return df


def user_preprocessing(tweet_df, user_processed):

    ### time processing
    user_processed['created_at'] = pd.to_datetime(user_processed['created_at'])

    ### renaming columns
    user_processed = user_processed.rename(
        columns={
            'id': 'author_id',
            'name': 'user_display_name',
            'description': 'user_desc',
            'created_at': 'user_created_at',
            'verified': 'user_verified',
            'protected': 'user_private',
            'followers_count': 'user_followers_cnt',
            'following_count': 'user_following_cnt',
            'tweet_count': 'user_tweet_count',
            'listed_count': 'user_list_count'
        })

    ### join in lag_hours (when available)
    if 'empty' not in tweet_df.columns:
        # locally create keep_non_zero function from utils for use
        def keep_non_zero(x):
            if x < 0:
                x = None
            return x

        # join
        tweet_df['author_id'] = tweet_df['author_id'].astype(str)
        tweet_df = tweet_df[['author_id', 'lag']]
        tweet_df['lag_hours'] = (pd.to_numeric(
            (tweet_df['lag'] / 60 / 60)) / 1000000000).apply(keep_non_zero)
        tweet_jn_lag = tweet_df[['author_id', 'lag_hours']].groupby(
            'author_id', as_index=False).agg({'lag_hours': 'std'})
        user_processed = user_processed.merge(tweet_jn_lag,
                                              on='author_id',
                                              how='left')
        # rename column
        user_processed = user_processed.rename(
            columns={'lag_hours': 'lag_hours_std'})
    else:
        user_processed['lag_hours_std'] = np.nan

        # relabel binary columns
    user_processed['user_verified'] = user_processed['user_verified'].map(
        lambda x: 1 if x == True else 0)
    user_processed['user_private'] = user_processed['user_private'].map(
        lambda x: 1 if x == True else 0)

    # keep columns of interest
    user_processed = user_processed[[
        'author_id', 'user_verified', 'user_private', 'user_followers_cnt',
        'user_following_cnt', 'user_tweet_count', 'user_list_count',
        'lag_hours_std'
    ]]

    return user_processed


def tweet_preprocessing(tweet_df, word2vec):
    tk = TweetTokenizer()
    tweet_df['clean_text'] = tweet_df['text'].apply(tokenize).apply(
        tk.tokenize).apply(remove_stopwords).apply(lemmatize)
    X = tweet_df[['clean_text']]
    X_embed = X['clean_text'].apply(lambda x: embed_sentence(word2vec, x))
    X_pad = pad_sequences(X_embed,dtype='float32',padding='post',maxlen=60)
    return X_pad
