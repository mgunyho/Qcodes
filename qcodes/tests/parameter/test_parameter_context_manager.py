from unittest import TestCase

from qcodes.tests.instrument_mocks import DummyInstrument
from qcodes.instrument.parameter import Parameter
import qcodes.utils.validators as vals


class TestSetContextManager(TestCase):

    def setUp(self):
        self.instrument = DummyInstrument('dummy_holder')

        self.instrument.add_parameter("a",
                                      set_cmd=None,
                                      get_cmd=None)

        # These two parameters mock actual instrument parameters; when first
        # connecting to the instrument, they have the _latest["value"] None.
        # We must call get() on them to get a valid value that we can set
        # them to in the __exit__ method of the context manager
        self.instrument.add_parameter("validated_param",
                                      set_cmd=self._vp_setter,
                                      get_cmd=self._vp_getter,
                                      vals=vals.Enum("foo", "bar"))

        self.instrument.add_parameter("parsed_param",
                                      set_cmd=self._pp_setter,
                                      get_cmd=self._pp_getter,
                                      set_parser=int)

        # A parameter that counts the number of times it has been set
        self.instrument.add_parameter("counting_parameter",
                                      set_cmd=self._cp_setter,
                                      get_cmd=self._cp_getter)

        # the mocked instrument state values of validated_param and
        # parsed_param
        self._vp_value = "foo"
        self._pp_value = 42

        # the counter value for counting_parameter
        self._cp_counter = 0
        self._cp_get_counter = 0

    def _vp_getter(self):
        return self._vp_value

    def _vp_setter(self, value):
        self._vp_value = value

    def _pp_getter(self):
        return self._pp_value

    def _pp_setter(self, value):
        self._pp_value = value

    def _cp_setter(self, value):
        self._cp_counter += 1

    def _cp_getter(self):
        self._cp_get_counter += 1
        return self.instrument['counting_parameter'].cache._value

    def tearDown(self):
        self.instrument.close()
        del self.instrument

    def test_set_to_none_when_parameter_is_not_captured_yet(self):
        counting_parameter = self.instrument.counting_parameter
        # Pre-conditions:
        assert self._cp_counter == 0
        assert self._cp_get_counter == 0
        assert counting_parameter.cache._value is None
        assert counting_parameter.get_latest.get_timestamp() is None

        with counting_parameter.set_to(None):
            # The value should not change
            assert counting_parameter.cache._value is None
            # The timestamp of the latest value should not be None anymore
            assert counting_parameter.get_latest.get_timestamp() is not None
            # Set method is not called
            assert self._cp_counter == 0
            # Get method is called once
            assert self._cp_get_counter == 1

        # The value should not change
        assert counting_parameter.cache._value is None
        # The timestamp of the latest value should still not be None
        assert counting_parameter.get_latest.get_timestamp() is not None
        # Set method is still not called
        assert self._cp_counter == 0
        # Get method is still called once
        assert self._cp_get_counter == 1

    def test_set_to_none_for_not_captured_parameter_but_instrument_has_value(self):
        # representing instrument here
        instr_value = 'something'
        set_counter = 0

        def set_instr_value(value):
            nonlocal instr_value, set_counter
            instr_value = value
            set_counter += 1

        # make a parameter that is linked to an instrument
        p = Parameter('p', set_cmd=set_instr_value, get_cmd=lambda: instr_value,
                      val_mapping={'foo': 'something', None: 'nothing'})

        # pre-conditions
        assert p.cache._value is None
        assert p.cache._raw_value is None
        assert p.cache.timestamp is None
        assert set_counter == 0

        with p.set_to(None):
            # assertions after entering the context
            assert set_counter == 1
            assert instr_value == 'nothing'
            assert p.cache._value is None
            assert p.cache._raw_value == 'nothing'
            assert p.cache.timestamp is not None

        # assertions after exiting the context
        assert set_counter == 2
        assert instr_value == 'something'
        assert p.cache._value == 'foo'
        assert p.cache._raw_value == 'something'
        assert p.cache.timestamp is not None

    def test_none_value(self):
        with self.instrument.a.set_to(3):
            assert self.instrument.a.get_latest.get_timestamp() is not None
            assert self.instrument.a.get() == 3
        assert self.instrument.a.get() is None
        assert self.instrument.a.get_latest.get_timestamp() is not None

    def test_context(self):
        self.instrument.a.set(2)

        with self.instrument.a.set_to(3):
            assert self.instrument.a.get() == 3
        assert self.instrument.a.get() == 2

    def test_validated_param(self):
        assert self.instrument.parsed_param.cache._value is None
        assert self.instrument.validated_param.get_latest() == "foo"
        with self.instrument.validated_param.set_to("bar"):
            assert self.instrument.validated_param.get() == "bar"
        assert self.instrument.validated_param.get_latest() == "foo"
        assert self.instrument.validated_param.get() == "foo"

    def test_parsed_param(self):
        assert self.instrument.parsed_param.cache._value is None
        assert self.instrument.parsed_param.get_latest() == 42
        with self.instrument.parsed_param.set_to(1):
            assert self.instrument.parsed_param.get() == 1
        assert self.instrument.parsed_param.get_latest() == 42
        assert self.instrument.parsed_param.get() == 42

    def test_number_of_set_calls(self):
        """
        Test that with param.set_to(X) does not perform any calls to set if
        the parameter already had the value X
        """
        assert self._cp_counter == 0
        self.instrument.counting_parameter(1)
        assert self._cp_counter == 1

        with self.instrument.counting_parameter.set_to(2):
            pass
        assert self._cp_counter == 3

        with self.instrument.counting_parameter.set_to(1):
            pass
        assert self._cp_counter == 3

    def test_freeze(self):
        self.instrument.a.set(2)

        with self.instrument.a.set_to(3, freeze=True):
            assert self.instrument.a() == 3
            assert not self.instrument.a.settable
            with self.assertRaises(TypeError):
                self.instrument.a.set(5)

        assert self.instrument.a.settable
        assert self.instrument.a() == 2

    def test_no_freeze(self):
        self.instrument.a.set(2)
        with self.instrument.a.set_to(3, freeze=False):
            assert self.instrument.a.settable
            assert self.instrument.a() == 3
            self.instrument.a.set(5)
            assert self.instrument.a() == 5
        assert self.instrument.a.settable
        assert self.instrument.a() == 2

    def test_context_initialized_with_current_value(self):
        """
        Test that if the context is entered with the current value of the
        parameter, but then changed inside, it gets properly set upon exiting
        """
        self.instrument.a.set(2)

        with self.instrument.a.set_to(2, freeze=False):
            assert self.instrument.a.get() == 2
            self.instrument.a.set(3)
            assert self.instrument.a() == 3

        assert self.instrument.a.get() == 2
