# -*- coding: utf-8 -*-
import os
import time
import unittest
from configparser import ConfigParser  # py3
from os import environ

from SetAPI.SetAPIImpl import SetAPI
from SetAPI.SetAPIServer import MethodContext
from SetAPI.authclient import KBaseAuth as _KBaseAuth
from installed_clients.FakeObjectsForTestsClient import FakeObjectsForTests
from installed_clients.WorkspaceClient import Workspace as workspaceService
from util import (
    info_to_ref,
    make_fake_diff_exp_matrix
)


class DifferentialExpressionMatrixSetAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        token = environ.get('KB_AUTH_TOKEN', None)
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('SetAPI'):
            cls.cfg[nameval[0]] = nameval[1]
        authServiceUrl = cls.cfg.get("auth-service-url",
                                     "https://kbase.us/services/authorization/Sessions/Login")
        auth_client = _KBaseAuth(authServiceUrl)
        user_id = auth_client.get_user(token)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': token,
                        'user_id': user_id,
                        'provenance': [
                            {'service': 'SetAPI',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        cls.wsURL = cls.cfg['workspace-url']
        cls.wsClient = workspaceService(cls.wsURL, token=token)
        cls.serviceImpl = SetAPI(cls.cfg)

        # setup data at the class level for now (so that the code is run
        # once for all tests, not before each test case.  Not sure how to
        # do that outside this function..)
        suffix = int(time.time() * 1000)
        wsName = "test_SetAPI_" + str(suffix)
        cls.wsClient.create_workspace({'workspace': wsName})
        cls.wsName = wsName

        foft = FakeObjectsForTests(os.environ['SDK_CALLBACK_URL'])

        # Make fake genomes
        [fake_genome, fake_genome2] = foft.create_fake_genomes({
            "ws_name": wsName,
            "obj_names": ["fake_genome", "fake_genome2"]
        })
        cls.genome_refs = [info_to_ref(fake_genome), info_to_ref(fake_genome2)]

        # Make fake diff exp matrices
        cls.diff_exps_no_genome = list()
        for i in range(3):
            cls.diff_exps_no_genome.append(
                make_fake_diff_exp_matrix(
                    "fake_mat_no_genome_{}".format(i), wsName, cls.wsClient
                )
            )

        cls.diff_exps_genome = list()
        for i in range(3):
            cls.diff_exps_genome.append(
                make_fake_diff_exp_matrix(
                    "fake_mat_genome_{}".format(i),
                    wsName,
                    cls.wsClient,
                    genome_ref=cls.genome_refs[0]
                )
            )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    def getWsClient(self):
        return self.__class__.wsClient

    def getWsName(self):
        return self.__class__.wsName

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    def test_save_diff_exp_matrix_set(self):
        set_name = "test_diff_exp_matrix_set"
        set_items = list()
        for ref in self.diff_exps_genome:
            set_items.append({
                "label": "foo",
                "ref": ref
            })
        matrix_set = {
            "description": "test_matrix_set",
            "items": set_items
        }
        result = self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
            "workspace": self.getWsName(),
            "output_object_name": set_name,
            "data": matrix_set
        })[0]
        self.assertIsNotNone(result)
        self.assertIn("set_ref", result)
        self.assertIn("set_info", result)
        self.assertEqual(result["set_ref"], info_to_ref(result["set_info"]))
        self.assertEqual(result["set_info"][1], set_name)
        self.assertIn("KBaseSets.DifferentialExpressionMatrixSet", result["set_info"][2])

    def test_save_diff_exp_matrix_set_no_genome(self):
        set_name = "test_de_matrix_set_no_genome"
        set_items = list()
        for ref in self.diff_exps_no_genome:
            set_items.append({
                "label": "foo",
                "ref": ref
            })
        matrix_set = {
            "description": "test_matrix_set",
            "items": set_items
        }
        result = self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
            "workspace": self.getWsName(),
            "output_object_name": set_name,
            "data": matrix_set
        })[0]
        self.assertIsNotNone(result)
        self.assertIn("set_ref", result)
        self.assertIn("set_info", result)
        self.assertEqual(result["set_ref"], info_to_ref(result["set_info"]))
        self.assertEqual(result["set_info"][1], set_name)
        self.assertIn("KBaseSets.DifferentialExpressionMatrixSet", result["set_info"][2])

    def test_save_dem_set_mismatched_genomes(self):
        set_name = "dem_set_bad_genomes"
        dem_set = {
            "description": "this_better_fail",
            "items": [{
                "ref": make_fake_diff_exp_matrix(
                    "odd_dem",
                    self.getWsName(),
                    self.getWsClient(),
                    genome_ref=self.genome_refs[1]
                ),
                "label": "odd_alignment"
            }, {
                "ref": self.diff_exps_genome[0],
                "label": "not_so_odd"
            }]
        }
        with self.assertRaises(ValueError) as err:
            self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
                "workspace": self.getWsName(),
                "output_object_name": set_name,
                "data": dem_set
            })
            self.assertIn("All Expression objects in the set must use "
                          "the same genome reference.", str(err.exception))

    def test_save_dem_set_no_data(self):
        with self.assertRaises(ValueError) as err:
            self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
                "workspace": self.getWsName(),
                "output_object_name": "foo",
                "data": None
            })
        self.assertIn('"data" parameter field required to save a DifferentialExpressionMatrixSet',
                      str(err.exception))

    def test_save_dem_set_no_dem(self):
        with self.assertRaises(ValueError) as err:
            self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
                "workspace": self.getWsName(),
                "output_object_name": "foo",
                "data": {
                    "items": []
                }
            })
        self.assertIn("A DifferentialExpressionMatrixSet must contain at "
                      "least one DifferentialExpressionMatrix object reference.",
                      str(err.exception))

    def test_get_dem_set(self):
        set_name = "test_expression_set"
        set_items = list()
        for ref in self.diff_exps_no_genome:
            set_items.append({
                "label": "wt",
                "ref": ref
            })
        dem_set = {
            "description": "test_test_diffExprMatrixSet",
            "items": set_items
        }
        dem_set_ref = self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
            "workspace": self.getWsName(),
            "output_object_name": set_name,
            "data": dem_set
        })[0]["set_ref"]

        fetched_set = self.getImpl().get_differential_expression_matrix_set_v1(self.getContext(), {
            "ref": dem_set_ref,
            "include_item_info": 0
        })[0]
        self.assertIsNotNone(fetched_set)
        self.assertIn("data", fetched_set)
        self.assertIn("info", fetched_set)
        self.assertEqual(len(fetched_set["data"]["items"]), 3)
        self.assertEqual(dem_set_ref, info_to_ref(fetched_set["info"]))
        for item in fetched_set["data"]["items"]:
            self.assertNotIn("info", item)
            self.assertIn("ref", item)
            self.assertNotIn("ref_path", item)
            self.assertIn("label", item)

        fetched_set_with_info = self.getImpl().get_differential_expression_matrix_set_v1(
            self.getContext(),
            {
                "ref": dem_set_ref,
                "include_item_info": 1
            }
        )[0]
        self.assertIsNotNone(fetched_set_with_info)
        self.assertIn("data", fetched_set_with_info)
        for item in fetched_set_with_info["data"]["items"]:
            self.assertIn("info", item)
            self.assertIn("ref", item)
            self.assertIn("label", item)

    def test_get_dem_set_ref_path(self):
        set_name = "test_diff_expression_set_ref_path"
        set_items = list()
        for ref in self.diff_exps_no_genome:
            set_items.append({
                "label": "wt",
                "ref": ref
            })
        dem_set = {
            "description": "test_diffExprMatrixSet_ref_path",
            "items": set_items
        }
        dem_set_ref = self.getImpl().save_differential_expression_matrix_set_v1(self.getContext(), {
            "workspace": self.getWsName(),
            "output_object_name": set_name,
            "data": dem_set
        })[0]["set_ref"]

        fetched_set_with_ref_path = self.getImpl().get_differential_expression_matrix_set_v1(self.getContext(), {
            "ref": dem_set_ref,
            "include_item_info": 0,
            "include_set_item_ref_paths": 1
        })[0]
        self.assertIsNotNone(fetched_set_with_ref_path)
        self.assertIn("data", fetched_set_with_ref_path)
        self.assertIn("info", fetched_set_with_ref_path)
        self.assertEqual(len(fetched_set_with_ref_path["data"]["items"]), 3)
        self.assertEqual(dem_set_ref, info_to_ref(fetched_set_with_ref_path["info"]))
        for item in fetched_set_with_ref_path["data"]["items"]:
            self.assertNotIn("info", item)
            self.assertIn("ref", item)
            self.assertIn("label", item)
            self.assertIn("ref_path", item)
            self.assertEqual(item["ref_path"], dem_set_ref + ';' + item["ref"])
        #pprint(fetched_set_with_ref_path)

    def test_get_dem_set_bad_ref(self):
        with self.assertRaises(ValueError) as err:
            self.getImpl().get_differential_expression_matrix_set_v1(self.getContext(), {
                "ref": "not_a_ref"
            })
        self.assertIn('"ref" parameter must be a valid workspace reference', str(err.exception))

    def test_get_dem_set_bad_path(self):
        with self.assertRaises(Exception):
            self.getImpl().get_differential_expression_matrix_set_v1(self.getContext(), {
                "ref": "1/2/3",
                "path_to_set": ["foo", "bar"]
            })

    def test_get_dem_set_no_ref(self):
        with self.assertRaises(ValueError) as err:
            self.getImpl().get_differential_expression_matrix_set_v1(self.getContext(), {
                "ref": None
            })
        self.assertIn('"ref" parameter field specifiying the DifferentialExpressionMatrix set is required',
                      str(err.exception))
