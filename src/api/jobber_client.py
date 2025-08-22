# jobber_client.py
#
#   handles all interactions with Jobber’s GraphQL API

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from config.settings import JOBBER_API_KEY, JOBBER_API_BASE

transport = RequestsHTTPTransport(
    url=JOBBER_API_BASE + '/graphql',
    headers={'Authorization': f'Bearer {JOBBER_API_KEY}'}
)
gql_client = Client(transport=transport, fetch_schema_from_transport=True)

def get_quote(quote_id):
    query = gql('''
    query GetQuote($id: ID!) {
        quote(id: $id) {
            id
            client { emails { address } properties { city } }
            amounts { totalPrice }
        }
    }
    ''')
    return gql_client.execute(query, variable_values={'id': quote_id})

def approve_quote(quote_id):
    mutation = gql('''
    mutation ApproveQuote($id: ID!) {
        quoteApprove(id: $id) {
            quote { id status }
            userErrors { message }
        }
    }
    ''')
    return gql_client.execute(mutation, variable_values={'id': quote_id})
