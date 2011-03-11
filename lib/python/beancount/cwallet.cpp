/**
 * A fast wallet object implemented in C
 * Most of the slowless in beancount is due to the wallet operations.
 *
 * Author: Martin Blais <blais@furius.ca>
 */

#include <Python.h>

#include <map>
#include <string>
#include <cstdint>
#include <iostream>



typedef std::map<PyObject*, int64_t> WalletMap;

typedef struct {
    PyObject_HEAD

    // Important note: we assume that all keys will be short strings, and that
    // they will all be using the Python string cache, and thus all instances of
    // string keys will point to the very same string objects. We same on memory
    // allocation.
    WalletMap mapping;
} Wallet;


const int64_t DIV = 1000000000;
const double fDIV = float(1000000000);

PyObject* decimal_ctor;

// Create and return a decimal from an integer.
PyObject* decimal_from_int(int64_t i)
{
    char buf[1024];
    snprintf(buf, 1024, "%.9f", i/fDIV);
    return PyObject_CallFunction(decimal_ctor, (char*)"s", buf);
}


PyGetSetDef Wallet_getset[] = {
    {NULL}
};

PyObject* Wallet_new(PyTypeObject* type, PyObject* args, PyObject* kwds)
{
    Wallet* self = (Wallet*)_PyObject_New(type);
    if (self == NULL) {
        return NULL;
    }

    self->mapping = WalletMap();

    return (PyObject*)self;
}

void Wallet_dealloc(PyObject* self)
{
    PyObject_Del(self);
}

PyObject* Wallet_str(PyObject* self)
{
    return PyString_FromStringAndSize("<Wallet>", 8);
}

#if 0
PyObject* Wallet_dump(PyObject* self, PyObject* offset_)
{
    if ( !PyInt_Check(offset_) ) {
        return NULL;
    }
    long offset = PyInt_AS_LONG(offset_);
    return Wallet_render(self, true, offset);
}
#endif

int Wallet_cmp(PyObject* o1, PyObject* o2)
{
/*FIXME: TODO*/
    if ( o1 == o2 ) {
        return 0;
    }
    return 1;
}

//------------------------------------------------------------------------------

// This function is used by PyMapping_Length() and PyObject_Size(), and has the
// same signature. This slot may be set to NULL if the object has no defined
// length.
Py_ssize_t Wallet_mapping_len(PyObject* self)
{
    return ((Wallet*)self)->mapping.size();
}

// This function is used by PyObject_GetItem() and has the same signature. This
// slot must be filled for the PyMapping_Check() function to return 1, it can be
// NULL otherwise.
PyObject* Wallet_mapping_getitem(PyObject* self, PyObject* key)
{
    if ( !PyString_Check(key) ) {
        PyErr_SetString(PyExc_IOError, "Invalid type for key.");
        return NULL;
    }

    WalletMap::const_iterator it = ((Wallet*)self)->mapping.find(key);
    if ( it == ((Wallet*)self)->mapping.end() ) {
        Py_RETURN_NONE;
    }

    return decimal_from_int(it->second);
}

// This function is used by PyObject_SetItem() and has the same signature. If
// this slot is NULL, the object does not support item assignment.
int Wallet_mapping_setitem(PyObject* self, PyObject* key, PyObject* value)
{
    ((Wallet*)self)->mapping.insert(WalletMap::value_type(key, 321123456789LL));
    return 0; // FIXME: TODO
}

PyMappingMethods Wallet_mapping = {
    Wallet_mapping_len,     /* mp_length */
    Wallet_mapping_getitem, /* mp_subscript */
    Wallet_mapping_setitem, /* mp_ass_subscript */
};



//------------------------------------------------------------------------------

PyMethodDef Wallet_methods[] = {
    /*{"_dump", (PyCFunction)Wallet_dump, METH_O, "Bla bla bla"},*/
    {NULL}
};

PyTypeObject Wallet_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                      /* ob_size */
    "Wallet",               /* tp_name */
    sizeof(Wallet),         /* tp_basicsize */
    0,                      /* tp_itemsize */
    Wallet_dealloc,         /* tp_dealloc */
    0,                      /* tp_print */
    0,                      /* tp_getattr */
    0,                      /* tp_setattr */
    Wallet_cmp,             /* tp_compare */
    Wallet_str,             /* tp_repr */
    0,                      /* tp_as_number */
    0,                      /* tp_as_sequence */
    &Wallet_mapping,        /* tp_as_mapping */
    0,                      /* tp_hash  */
    0,                      /* tp_call */
    Wallet_str,             /* tp_str */
    0,                      /* tp_getattro */
    0,                      /* tp_setattro */
    0,                      /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,     /* tp_flags */
    "A fast Wallet class.", /* tp_doc */
    0,                      /* tp_traverse */
    0,                      /* tp_clear */
    0,                      /* tp_richcompare */
    0,                      /* tp_weaklistoffset */
    0,                      /* tp_iter */
    0,                      /* tp_iternext */
    Wallet_methods,         /* tp_methods */
    0,                      /* tp_members */
    Wallet_getset,          /* tp_getset */
    0,                      /* tp_base */
    0,                      /* tp_dict */
    0,                      /* tp_descr_get */
    0,                      /* tp_descr_set */
    0,                      /* tp_dictoffset */
    0,                      /* tp_init */
    0,                      /* tp_alloc */
    Wallet_new,             /* tp_new */
};

static PyMethodDef module_methods[] = {
    {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC initcwallet(void)
{
    PyObject* module = Py_InitModule("cwallet", module_methods);

    if (PyType_Ready(&Wallet_Type) < 0)
        return;
    Py_INCREF((PyObject*)&Wallet_Type);
    PyModule_AddObject(module, "Wallet", (PyObject*)&Wallet_Type);

    PyObject* decimal = PyImport_ImportModule("decimal");
    decimal_ctor = PyObject_GetAttrString(decimal, "Decimal");
    std::cout << "decimal_ctor = " << decimal_ctor << std::endl;

}

