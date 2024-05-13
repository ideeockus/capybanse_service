import asyncio

from rec_utils import get_recommendation_for_user
from rec_utils import get_recommendation_for_user_query

if __name__ == '__main__':
    recs = asyncio.run(get_recommendation_for_user_query(
        1,
        'Привет! мне нравятся роботы, всякие умные дома, 3d принтеры и всякое такое'
    ))

    print('RECOMMENDATION got')
    for rec in recs:
        print(rec)


