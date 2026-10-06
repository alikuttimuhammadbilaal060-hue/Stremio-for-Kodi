import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'core'))
from account import pull_user_id,AccountError
class AccountIdentityTests(unittest.TestCase):
    def test_rotated_tokens_return_same_server_identity_without_profile_data(self):
        with patch('account.request',return_value={'result':{'_id':'stable-user','email':'private@example.test','trakt':{'access_token':'private'}}}) as request:
            self.assertEqual(pull_user_id('first-token'),'stable-user')
            self.assertEqual(pull_user_id('rotated-token'),'stable-user')
            self.assertEqual(request.call_args.args,('https://api.strem.io/api/getUser',{'type':'GetUser','authKey':'rotated-token'}))
    def test_missing_or_malformed_identity_never_invents_account(self):
        for value in (None,[],{}, {'_id':''},{'_id':True},{'_id':' user '},{'_id':'x'*161}):
            with self.subTest(value=value),patch('account.request',return_value={'result':value}):
                with self.assertRaises(AccountError):pull_user_id('fixture-token')
if __name__=='__main__':unittest.main()
